"""A real HEIC built for the tests, shaped like an iPhone's: the picture is a grid of HEVC tiles (a "grid" item that
refers to its tiles) and is stored sideways with HEIF's own rotation property (irot), the way the camera saves a photo
taken upright. ffmpeg (libx265) encodes the tiles; the HEIF boxes are written here (ISO/IEC 23008-12), since ffmpeg
has no HEIF muxer and Pillow no HEIF plugin by default."""
import struct
import tempfile
from pathlib import Path

from conftest import ffmpeg


def _box(kind, payload):
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def _full(kind, version, flags, payload):
    return _box(kind, struct.pack(">I", (version << 24) | flags) + payload)


def _nals(annexb):
    """The NAL units of an Annex B stream."""
    out, i, n = [], 0, len(annexb)
    starts = []
    while i < n - 3:
        if annexb[i:i + 3] == b"\x00\x00\x01":
            starts.append(i + 3)
            i += 3
        else:
            i += 1
    for k, s in enumerate(starts):
        e = starts[k + 1] - 3 if k + 1 < len(starts) else n
        nal = annexb[s:e]
        while nal.endswith(b"\x00") and k + 1 < len(starts):
            nal = nal[:-1]
        out.append(nal)
    return out


def _hvcc(params):
    """An hvcC box from the VPS, SPS and PPS (Main profile, 8 bits, 4:2:0)."""
    head = bytes([1, 0x01]) + struct.pack(">I", 0x60000000) + bytes([0x90, 0, 0, 0, 0, 0]) + bytes([93])
    head += struct.pack(">H", 0xF000) + bytes([0xFC, 0xFD, 0xF8, 0xF8]) + struct.pack(">H", 0) + bytes([0x0F])
    arrays = b""
    for nal in params:
        typ = (nal[0] >> 1) & 0x3F
        arrays += bytes([0x80 | typ]) + struct.pack(">HH", 1, len(nal)) + nal
    return _box(b"hvcC", head + bytes([len(params)]) + arrays)


def make_heic(path, tiles, tile_w, tile_h, rotation=0):
    """tiles: colors of the tiles, left to right in one row, as stored; rotation: irot, anticlockwise quarter turns
    (an iPhone photo taken upright is stored on its side with 3). Returns the path."""
    tmp = Path(tempfile.mkdtemp(prefix="heif-"))
    datas, params = [], None
    for j, color in enumerate(tiles):
        raw = tmp / f"t{j}.hevc"
        ffmpeg("-f", "lavfi", "-i", f"color=c={color}:size={tile_w}x{tile_h}:rate=1:duration=1", "-frames:v", "1",
               "-c:v", "libx265", "-pix_fmt", "yuv420p", "-x265-params", "log-level=error:keyint=1:annexb=1",
               "-f", "hevc", raw)
        nals = _nals(raw.read_bytes())
        ps = [x for x in nals if ((x[0] >> 1) & 0x3F) in (32, 33, 34)]
        vcl = [x for x in nals if ((x[0] >> 1) & 0x3F) < 32]
        params = params or ps
        datas.append(b"".join(struct.pack(">I", len(x)) + x for x in vcl))
    cols = len(tiles)
    out_w, out_h = tile_w * cols, tile_h
    grid = bytes([0, 0, 0, cols - 1]) + struct.pack(">HH", out_w, out_h)
    GRID = 1
    ids = list(range(2, 2 + cols))
    items = [(GRID, grid)] + list(zip(ids, datas))

    ftyp = _box(b"ftyp", b"heic" + struct.pack(">I", 0) + b"mif1heic")

    def meta(offsets):
        hdlr = _full(b"hdlr", 0, 0, struct.pack(">I", 0) + b"pict" + b"\x00" * 12 + b"\x00")
        pitm = _full(b"pitm", 0, 0, struct.pack(">H", GRID))
        infe = [_full(b"infe", 2, 0, struct.pack(">HH", GRID, 0) + b"grid" + b"\x00")]
        infe += [_full(b"infe", 2, 0, struct.pack(">HH", i, 0) + b"hvc1" + b"\x00") for i in ids]
        iinf = _full(b"iinf", 0, 0, struct.pack(">H", len(infe)) + b"".join(infe))
        dimg = _box(b"dimg", struct.pack(">HH", GRID, cols) + b"".join(struct.pack(">H", i) for i in ids))
        iref = _full(b"iref", 0, 0, dimg)
        ipco = _box(b"ipco", _hvcc(params) + _full(b"ispe", 0, 0, struct.pack(">II", tile_w, tile_h))
                    + _full(b"ispe", 0, 0, struct.pack(">II", out_w, out_h)) + _box(b"irot", bytes([rotation & 3])))
        assoc = [struct.pack(">HB", GRID, 2) + bytes([3, 0x80 | 4])]  # the grid: its size, its rotation (essential)
        assoc += [struct.pack(">HB", i, 2) + bytes([0x80 | 1, 2]) for i in ids]  # a tile: hvcC, its size
        ipma = _full(b"ipma", 0, 0, struct.pack(">I", len(assoc)) + b"".join(assoc))
        iprp = _box(b"iprp", ipco + ipma)
        loc = b"".join(struct.pack(">HHHII", i, 0, 1, off, len(d)) for (i, d), off in zip(items, offsets))
        iloc = _full(b"iloc", 0, 0, bytes([0x44, 0x00]) + struct.pack(">H", len(items)) + loc)
        return _full(b"meta", 0, 0, hdlr + pitm + iloc + iinf + iref + iprp)

    head = len(ftyp) + len(meta([0] * len(items))) + 8  # the mdat header
    offsets, cur = [], head
    for _, d in items:
        offsets.append(cur)
        cur += len(d)
    body = ftyp + meta(offsets) + _box(b"mdat", b"".join(d for _, d in items))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(body)
    for f in tmp.iterdir():
        f.unlink()
    tmp.rmdir()
    return Path(path)
