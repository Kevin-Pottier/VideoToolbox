import json
from fractions import Fraction

import pytest

import compression
import encoders
import hdr
from audio_tracks import MediaFileInfo, VideoTrackInfo
from compression import CompressionSettings, hdr_mode
from encoders import BY_NAME

PQ_VIDEO = VideoTrackInfo(0, "hevc", 3840, 2160, pix_fmt="yuv420p10le", color_transfer="smpte2084",
                          color_primaries="bt2020", color_space="bt2020nc")
HLG_VIDEO = VideoTrackInfo(0, "hevc", 3840, 2160, pix_fmt="yuv420p10le", color_transfer="arib-std-b67",
                           color_primaries="bt2020", color_space="bt2020nc")
SDR_VIDEO = VideoTrackInfo(0, "h264", 1920, 1080, pix_fmt="yuv420p", color_transfer="bt709")
# As ffprobe reports the first frame of an HDR10 movie
FFPROBE_FRAME = {"frames": [{"side_data_list": [
    {"side_data_type": "H.26[45] User Data Unregistered SEI message"},
    {"side_data_type": "Mastering display metadata", "red_x": "34000/50000", "red_y": "16000/50000",
     "green_x": "13250/50000", "green_y": "34500/50000", "blue_x": "7500/50000", "blue_y": "3000/50000",
     "white_point_x": "15635/50000", "white_point_y": "16450/50000", "min_luminance": "50/10000",
     "max_luminance": "10000000/10000"},
    {"side_data_type": "Content light level metadata", "max_content": 1000, "max_average": 400},
]}]}
METADATA = hdr.StaticMetadata((Fraction(13250, 50000), Fraction(34500, 50000)), (Fraction(7500, 50000), Fraction(3000, 50000)),
                              (Fraction(34000, 50000), Fraction(16000, 50000)), (Fraction(15635, 50000), Fraction(16450, 50000)),
                              Fraction(1000), Fraction(5, 1000), 1000, 400)


def movie(video):
    return MediaFileInfo("in.mkv", video_tracks=[video])


def option(cmd, name):
    return cmd[cmd.index(name) + 1]


@pytest.mark.parametrize("video, encoder, settings, burn, mode", [
    (SDR_VIDEO, "libx265", CompressionSettings(), False, None),
    (PQ_VIDEO, "libx265", CompressionSettings(), False, "keep"),
    (PQ_VIDEO, "hevc_nvenc", CompressionSettings(), False, "keep"),
    (HLG_VIDEO, "libsvtav1", CompressionSettings(), False, "keep"),
    (PQ_VIDEO, "libx264", CompressionSettings(), False, "sdr"),           # H.264 cannot keep the HDR
    (PQ_VIDEO, "h264_qsv", CompressionSettings(), False, "sdr"),
    (PQ_VIDEO, "libx265", CompressionSettings(hdr_to_sdr=True), False, "sdr"),
    (PQ_VIDEO, "libx265", CompressionSettings(), True, "sdr"),            # burned subtitles would be blinding
])
def test_hdr_mode(video, encoder, settings, burn, mode):
    assert hdr_mode(movie(video), BY_NAME[encoder], settings, burn) == mode


@pytest.mark.parametrize("name, vf", [
    ("libx265", "format=yuv420p10le"),
    ("libsvtav1", "format=yuv420p10le"),
    ("hevc_nvenc", "format=p010le"),
    ("av1_qsv", "format=p010le"),
    ("hevc_vaapi", "format=p010,hwupload"),
])
def test_ten_bit_frames_for_each_encoder_family(name, vf):
    assert option(encoders.filter_args(BY_NAME[name], ten_bit=True), "-vf") == vf


def test_gpu_hevc_encoders_need_the_main10_profile():
    assert encoders.ten_bit_args(BY_NAME["hevc_nvenc"]) == ["-profile:v", "main10"]
    assert encoders.ten_bit_args(BY_NAME["hevc_videotoolbox"]) == ["-profile:v", "main10"]
    assert encoders.ten_bit_args(BY_NAME["libx265"]) == encoders.ten_bit_args(BY_NAME["av1_nvenc"]) == []


def test_static_metadata_read_from_the_first_frame(monkeypatch):
    class Result:
        stdout = json.dumps(FFPROBE_FRAME)
    monkeypatch.setattr(hdr.subprocess, "run", lambda *args, **kwargs: Result())
    assert hdr.read_static_metadata("in.mkv") == METADATA


def test_no_static_metadata(monkeypatch):
    class Result:
        stdout = json.dumps({"frames": [{"side_data_list": []}]})
    monkeypatch.setattr(hdr.subprocess, "run", lambda *args, **kwargs: Result())
    assert hdr.read_static_metadata("in.mkv") is None


def test_x265_gets_the_hdr10_metadata_in_its_units():
    # 0.00002 for the chromaticities, 0.0001 cd/m² for the luminance
    assert hdr.x265_params(PQ_VIDEO, METADATA) == [
        "repeat-headers=1", "hdr10=1", "hdr10-opt=1",
        "master-display=G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(10000000,50)", "max-cll=1000,400"]
    assert hdr.x265_params(PQ_VIDEO, None) == ["repeat-headers=1", "hdr10=1", "hdr10-opt=1"]
    assert hdr.x265_params(HLG_VIDEO, None) == ["repeat-headers=1"]  # HLG has no static metadata


def test_svtav1_gets_the_hdr10_metadata_as_plain_numbers():
    assert hdr.svtav1_params(METADATA) == ["-svtav1-params", "mastering-display=G(0.2650,0.6900)B(0.1500,0.0600)"
                                           "R(0.6800,0.3200)WP(0.3127,0.3290)L(1000.0000,0.0050):content-light=1000,400"]
    assert hdr.svtav1_params(None) == []


def commands(video, encoder, settings=CompressionSettings(), sub_option="none", metadata=None):
    from compression import build_encode_commands
    return build_encode_commands("in.mkv", "out.mkv", "mkv", 4000, sub_option, "work/subtitles.srt", "work",
                                 movie(video), "-fps_mode", BY_NAME[encoder], settings, metadata)


def test_hdr_kept_by_x265_in_both_passes():
    for cmd, _ in commands(PQ_VIDEO, "libx265", metadata=METADATA):
        assert option(cmd, "-vf") == "format=yuv420p10le"
        assert (option(cmd, "-color_primaries"), option(cmd, "-color_trc"), option(cmd, "-colorspace")) == (
            "bt2020", "smpte2084", "bt2020nc")
        assert "master-display=G(13250,34500)" in option(cmd, "-x265-params")


def test_hdr_converted_to_sdr_before_the_resize_and_the_subtitles():
    settings = CompressionSettings(max_height=1080)
    cmd = commands(PQ_VIDEO, "libx264", settings, sub_option="hard")[1][0]
    assert option(cmd, "-vf") == (hdr.TONEMAP_FILTER + ",scale=-2:1080:flags=lanczos,subtitles=subtitles.srt,"
                                  "format=yuv420p")
    assert (option(cmd, "-color_primaries"), option(cmd, "-color_trc"), option(cmd, "-colorspace")) == (
        "bt709", "bt709", "bt709")


def test_sdr_videos_are_unchanged():
    cmd = commands(SDR_VIDEO, "libx265")[1][0]
    assert option(cmd, "-vf") == "format=yuv420p" and "-color_trc" not in cmd and "hdr10" not in option(cmd, "-x265-params")


@pytest.fixture
def big_file(tmp_path):
    path = tmp_path / "movie.mkv"
    path.write_bytes(b"\0" * 2_000_000)  # larger than the target: no copy shortcut
    return str(path)


def test_dolby_vision_profile_5_is_refused(monkeypatch, big_file):
    video = VideoTrackInfo(0, "hevc", 3840, 2160, color_transfer="smpte2084", dv_profile=5)
    monkeypatch.setattr(compression, "ffprobe_streams", lambda path: MediaFileInfo(path, video_tracks=[video],
                                                                                   duration=10.0))
    with pytest.raises(compression.CompressionError, match="Dolby Vision profile 5"):
        compression.run_compression(big_file, "none", None, "mkv", 0.001, gui_progress=lambda *a: None,
                                    encoder=BY_NAME["libx265"])


def test_sdr_conversion_without_zscale_is_explained(monkeypatch, big_file):
    monkeypatch.setattr(compression, "ffprobe_streams", lambda path: MediaFileInfo(path, video_tracks=[PQ_VIDEO],
                                                                                   duration=10.0))
    monkeypatch.setattr(hdr, "has_zscale", lambda: False)
    with pytest.raises(compression.CompressionError, match="zscale"):
        compression.run_compression(big_file, "none", None, "mkv", 0.001, gui_progress=lambda *a: None)
