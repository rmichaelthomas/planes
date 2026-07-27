#!/usr/bin/env python3
"""
planes — logo render pipeline.

The logo is 3D geometry: four grid planes crossing at a shared origin.
Three are mutually orthogonal (the coordinate planes); the fourth is
oblique, cutting across where the other three meet.

This file is the single source of truth. Every flat asset (SVG, and any
raster derived from it) is a projection emitted from here. To change the
mark, change the data at the top and re-run — never hand-edit an output.

    python3 render_logo.py

No dependencies.
"""

import math
import os

# ---------------------------------------------------------------------------
# GEOMETRY — the mark itself
# ---------------------------------------------------------------------------

HALF = 60.0        # half-width of each plane
AXIS = 90.0        # half-length of the axis lines (extend past the planes)
DIVISIONS = 6      # grid cells per side; controls interior line density

# Each plane: two orthonormal basis vectors spanning it, plus a color.
# Order here is paint order, back to front.
PLANES = [
    {
        "name": "rule",
        "color": "#F59E0B",
        "u": (1.0, 0.0, 0.0),
        "v": (0.0, 0.0, 1.0),
    },
    {
        "name": "instruction",
        "color": "#3B82F6",
        "u": (1.0, 0.0, 0.0),
        "v": (0.0, 1.0, 0.0),
    },
    {
        "name": "annotation",
        "color": "#14B8A6",
        "u": (0.0, 0.0, 1.0),
        "v": (0.0, 1.0, 0.0),
    },
    {
        "name": "record",
        "color": "#8B5CF6",
        # Oblique: spans a direction that lies in none of the coordinate
        # planes, so it genuinely cuts across all three.
        "u": (0.7071, 0.0, -0.7071),
        "v": (0.4082, 0.8165, 0.4082),
    },
]

AXES = [
    ((1.0, 0.0, 0.0), "x"),
    ((0.0, 1.0, 0.0), "y"),
    ((0.0, 0.0, 1.0), "z"),
]

# ---------------------------------------------------------------------------
# CAMERA — how the geometry gets flattened
# ---------------------------------------------------------------------------
# yaw   : rotation about the vertical axis (turns the model)
# pitch : rotation about the horizontal axis (tips it toward the viewer)
#
# A near-isometric angle (35.264 pitch / 45 yaw) makes all three coordinate
# planes symmetrical, which flattens the depth cue that distinguishes them.
# A three-quarter view keeps the planes receding at different rates, so the
# orthogonality — and the obliqueness of the fourth plane — stays legible.

# Per-view overrides. Any of DIVISIONS / axis_width / origin_r / plane_stroke
# / fill_opacity may be set per view; unset keys fall back to the defaults
# above. Verified at 16-64px: interior grid lines are the first thing to die
# on downsampling, so the small view drops them entirely (divisions=0) and
# thickens the ink instead.
VIEWS = {
    "hero": {"yaw": 32.0, "pitch": 24.0, "size": 280},
    "mark": {"yaw": 38.0, "pitch": 28.0, "size": 280},
    "small": {
        "yaw": 38.0,
        "pitch": 28.0,
        "size": 240,
        "divisions": 0,
        "axis_width": 7.0,
        "origin_r": 11.0,
        "plane_stroke": 5.0,
        "fill_opacity": 0.42,
    },
}

INK_LIGHT = "#1A1A1A"   # for placement on light backgrounds
INK_DARK = "#F2F2F2"    # for placement on dark backgrounds

OUT_DIR = os.environ.get(
    "PLANES_OUT", os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# PROJECTION
# ---------------------------------------------------------------------------

def rotate(p, yaw_deg, pitch_deg):
    """Rotate a 3D point by yaw (about Y) then pitch (about X)."""
    yaw = math.radians(yaw_deg)
    pitch = math.radians(pitch_deg)
    x, y, z = p
    # yaw about Y
    x, z = x * math.cos(yaw) + z * math.sin(yaw), -x * math.sin(yaw) + z * math.cos(yaw)
    # pitch about X
    y, z = y * math.cos(pitch) - z * math.sin(pitch), y * math.sin(pitch) + z * math.cos(pitch)
    return (x, y, z)


def project(p, yaw, pitch):
    """3D point -> 2D SVG coords. Orthographic; SVG y grows downward."""
    x, y, _ = rotate(p, yaw, pitch)
    return (x, -y)


def fmt(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


def pt(p, yaw, pitch):
    x, y = project(p, yaw, pitch)
    return f"{fmt(x)},{fmt(y)}"


def scale(vec, k):
    return (vec[0] * k, vec[1] * k, vec[2] * k)


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


# ---------------------------------------------------------------------------
# EMISSION
# ---------------------------------------------------------------------------

def plane_svg(plane, yaw, pitch, style):
    u, v, color = plane["u"], plane["v"], plane["color"]
    divisions = style.get("divisions", DIVISIONS)
    stroke = style.get("plane_stroke", 1.6)
    fill_op = style.get("fill_opacity", 0.26)
    parts = []

    corners = [
        add(scale(u, -HALF), scale(v, -HALF)),
        add(scale(u, HALF), scale(v, -HALF)),
        add(scale(u, HALF), scale(v, HALF)),
        add(scale(u, -HALF), scale(v, HALF)),
    ]
    poly = " ".join(pt(c, yaw, pitch) for c in corners)
    parts.append(
        f'  <polygon points="{poly}" fill="{color}" fill-opacity="{fill_op}" '
        f'stroke="{color}" stroke-opacity="0.9" stroke-width="{fmt(stroke)}"/>'
    )

    if divisions < 2:
        return parts

    step = (2 * HALF) / divisions
    for i in range(1, divisions):
        off = -HALF + i * step
        a = add(scale(u, off), scale(v, -HALF))
        b = add(scale(u, off), scale(v, HALF))
        parts.append(
            f'  <line x1="{fmt(project(a, yaw, pitch)[0])}" y1="{fmt(project(a, yaw, pitch)[1])}" '
            f'x2="{fmt(project(b, yaw, pitch)[0])}" y2="{fmt(project(b, yaw, pitch)[1])}" '
            f'stroke="{color}" stroke-opacity="0.45" stroke-width="0.9"/>'
        )
        c = add(scale(v, off), scale(u, -HALF))
        d = add(scale(v, off), scale(u, HALF))
        parts.append(
            f'  <line x1="{fmt(project(c, yaw, pitch)[0])}" y1="{fmt(project(c, yaw, pitch)[1])}" '
            f'x2="{fmt(project(d, yaw, pitch)[0])}" y2="{fmt(project(d, yaw, pitch)[1])}" '
            f'stroke="{color}" stroke-opacity="0.45" stroke-width="0.9"/>'
        )
    return parts


def render(yaw, pitch, size, ink, style=None):
    style = style or {}
    axis_w = style.get("axis_width", 2.0)
    origin_r = style.get("origin_r", 4.0)
    half = size / 2
    out = [
        f'<svg viewBox="{fmt(-half)} {fmt(-half)} {size} {size}" '
        'xmlns="http://www.w3.org/2000/svg" role="img">',
        "<title>planes</title>",
        "<desc>Four grid planes crossing at a shared origin: three mutually "
        "orthogonal coordinate planes and one oblique plane cutting across them.</desc>",
    ]

    for plane in PLANES:
        out.extend(plane_svg(plane, yaw, pitch, style))

    for direction, _label in AXES:
        a = scale(direction, -AXIS)
        b = scale(direction, AXIS)
        out.append(
            f'  <line x1="{fmt(project(a, yaw, pitch)[0])}" y1="{fmt(project(a, yaw, pitch)[1])}" '
            f'x2="{fmt(project(b, yaw, pitch)[0])}" y2="{fmt(project(b, yaw, pitch)[1])}" '
            f'stroke="{ink}" stroke-width="{fmt(axis_w)}"/>'
        )

    out.append(f'  <circle cx="0" cy="0" r="{fmt(origin_r)}" fill="{ink}"/>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


SHEET_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>planes — visual identity master sheet</title>
<style>
  :root {{
    --ink: #1a1a1a; --muted: #6b6b6b; --line: #e3e3e0; --bg: #fbfbf9;
    --card: #ffffff; --code-bg: #f4f4f1;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --ink:#f2f2f2; --muted:#9a9a97; --line:#2c2c2a; --bg:#0f0f0e;
            --card:#171716; --code-bg:#1d1d1b; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; padding:3rem 1.5rem 5rem; background:var(--bg); color:var(--ink);
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
         line-height:1.65; }}
  .wrap {{ max-width: 860px; margin: 0 auto; }}
  header {{ border-bottom:1px solid var(--line); padding-bottom:2rem; margin-bottom:2.5rem; }}
  h1 {{ font-size:2rem; font-weight:500; margin:0 0 .35rem; letter-spacing:-.01em; }}
  h2 {{ font-size:1.15rem; font-weight:500; margin:3rem 0 1rem; padding-bottom:.5rem;
       border-bottom:1px solid var(--line); }}
  h3 {{ font-size:.95rem; font-weight:500; margin:1.75rem 0 .6rem; }}
  p {{ margin:.65rem 0; }}
  .sub {{ color:var(--muted); font-size:.95rem; margin:0; }}
  code, pre {{ font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }}
  code {{ background:var(--code-bg); padding:.12em .4em; border-radius:4px; font-size:.88em; }}
  pre {{ background:var(--code-bg); border:1px solid var(--line); border-radius:8px;
        padding:1rem 1.15rem; overflow-x:auto; font-size:.82rem; line-height:1.6; }}
  pre code {{ background:none; padding:0; font-size:inherit; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:1rem; }}
  .swatch-row {{ display:flex; align-items:center; gap:.7rem; padding:.5rem 0;
                border-bottom:1px solid var(--line); }}
  .swatch-row:last-child {{ border-bottom:none; }}
  .chip {{ width:26px; height:26px; border-radius:5px; flex:none; }}
  .swatch-meta {{ font-size:.85rem; }}
  .swatch-meta .hex {{ color:var(--muted); font-family:ui-monospace,monospace; font-size:.78rem; }}
  table {{ width:100%; border-collapse:collapse; font-size:.87rem; margin:1rem 0; }}
  th, td {{ text-align:left; padding:.55rem .5rem; border-bottom:1px solid var(--line);
           vertical-align:top; }}
  th {{ font-weight:500; color:var(--muted); font-size:.78rem; letter-spacing:.05em;
       text-transform:uppercase; }}
  td code {{ font-size:.82em; }}
  .note {{ border-left:3px solid #F59E0B; background:var(--card); padding:.85rem 1.1rem;
          border-radius:0 6px 6px 0; font-size:.9rem; margin:1.25rem 0; }}
  .specimen {{ background:var(--card); border:1px solid var(--line); border-radius:10px;
              padding:1.5rem; display:flex; gap:1.5rem; align-items:center;
              justify-content:center; flex-wrap:wrap; }}
  .specimen.dark {{ background:#0b0b0b; border-color:#262626; }}
  .spec svg {{ display:block; }}
  .cap {{ text-align:center; font-size:.75rem; color:var(--muted); margin-top:.5rem; }}
  footer {{ margin-top:4rem; padding-top:1.5rem; border-top:1px solid var(--line);
           font-size:.83rem; color:var(--muted); }}
</style>
</head>
<body>
<div class="wrap">

<header>
  <h1>planes — visual identity</h1>
  <p class="sub">Master sheet and generation instructions · rough marker, not locked · July 24, 2026</p>
</header>

<h2>The mark</h2>
<p>Four grid planes crossing at a shared origin. Three are mutually orthogonal — the XY, XZ, and YZ coordinate planes. The fourth is oblique, sitting at roughly 54.7° to all three, cutting across the point where they meet.</p>
<p>The mark is <strong>3D geometry</strong>. Every flat file is a projection of it at a chosen camera angle, not a drawing. There is no canonical 2D artwork to edit — there is a canonical geometry and a render script.</p>

<div class="note">
<strong>Known limit of the 2D stills.</strong> A static projection cannot assert orthogonality; that is a 3D fact and a flat image has no way to carry it. In a still, the four planes read as "four planes at various angles." The animated version is where the structural claim — three perpendicular, one crossing — is actually legible. Treat the stills as the compressed form.
</div>

<h2>Plane colors</h2>
<p>Provisional. The plane-to-color mapping is written down so it stops being arbitrary, but nothing here is locked.</p>
<div class="card">
{swatches}
</div>
<p>Ink (axes, origin, wordmark) is the only thing that flips between backgrounds: <code>#1A1A1A</code> on light, <code>#F2F2F2</code> on dark. Plane colors are identical in both.</p>

<h2>Specimens</h2>
<p>Every specimen below is inlined SVG. This sheet has no external file dependencies and renders correctly from any location.</p>
<div class="specimen">
{light_row}
</div>
<div class="specimen dark" style="margin-top:1rem;">
{dark_row}
</div>

<h2>Which variant to use</h2>
<table>
  <thead><tr><th>Variant</th><th>Use for</th><th>Notes</th></tr></thead>
  <tbody>
    <tr><td><code>hero</code></td><td>Site headers, README, docs landing, slides</td>
        <td>Shallower angle; most legible depth.</td></tr>
    <tr><td><code>mark</code></td><td>General-purpose icon at 64px and above</td>
        <td>Full grid detail. Degrades below ~48px.</td></tr>
    <tr><td><code>small</code></td><td>Favicon, avatar, anything under 48px</td>
        <td>No interior grid, heavier axes and origin.</td></tr>
    <tr><td><code>animated</code></td><td>Web hero, loading state, splash</td>
        <td>The only form that carries the full structural claim.</td></tr>
  </tbody>
</table>

<div class="note">
<strong>Verified at small sizes.</strong> Rasterized and inspected at 16, 24, 32, 48, and 64px. The <code>mark</code> variant turns to mud below 48px — interior grid lines are the first thing to die on downsampling. The <code>small</code> variant drops them entirely and thickens the ink; its origin dot and axis lines survive to 16px. At 16px it reads as a distinct shape rather than four legible planes, which is the honest floor for a four-plane crossing at that resolution.
</div>

<h2>Generating assets</h2>
<p><code>render_logo.py</code> is the source of truth. It has no dependencies and writes one SVG per view per ink color, plus this sheet.</p>
<pre><code>python3 render_logo.py</code></pre>
<p>Output goes to <code>/mnt/user-data/outputs</code> by default; override with the <code>PLANES_OUT</code> environment variable:</p>
<pre><code>PLANES_OUT=./assets python3 render_logo.py</code></pre>
<p>Files are named <code>planes-{{view}}-on-{{light|dark}}.svg</code>. This sheet is regenerated too — edit the template in the script, never the emitted HTML.</p>

<h3>Adding a camera angle</h3>
<p>Add an entry to <code>VIEWS</code> and re-run. Two SVGs appear for it automatically, and it joins the specimen rows above.</p>
<pre><code>VIEWS = {{
    "hero":  {{"yaw": 32.0, "pitch": 24.0, "size": 280}},
    "mark":  {{"yaw": 38.0, "pitch": 28.0, "size": 280}},
    "small": {{"yaw": 38.0, "pitch": 28.0, "size": 240,
              "divisions": 0, "axis_width": 7.0, "origin_r": 11.0,
              "plane_stroke": 5.0, "fill_opacity": 0.42}},
    "wide":  {{"yaw": 55.0, "pitch": 15.0, "size": 280}},
}}</code></pre>

<h3>View parameters</h3>
<table>
  <thead><tr><th>Key</th><th>Meaning</th><th>Default</th></tr></thead>
  <tbody>
    <tr><td><code>yaw</code></td><td>Rotation about the vertical axis, degrees</td><td>—</td></tr>
    <tr><td><code>pitch</code></td><td>Tip toward the viewer, degrees</td><td>—</td></tr>
    <tr><td><code>size</code></td><td>SVG viewBox edge length</td><td>—</td></tr>
    <tr><td><code>divisions</code></td><td>Grid cells per side; <code>0</code> or <code>1</code> omits interior lines</td><td><code>6</code></td></tr>
    <tr><td><code>axis_width</code></td><td>Stroke width of the x/y/z lines</td><td><code>2.0</code></td></tr>
    <tr><td><code>origin_r</code></td><td>Radius of the origin dot</td><td><code>4.0</code></td></tr>
    <tr><td><code>plane_stroke</code></td><td>Stroke width of each plane's border</td><td><code>1.6</code></td></tr>
    <tr><td><code>fill_opacity</code></td><td>Plane fill opacity</td><td><code>0.26</code></td></tr>
  </tbody>
</table>
<p>Avoid a near-isometric angle (yaw 45 / pitch 35.264). It makes the three coordinate planes symmetrical, which flattens the exact depth cue needed to tell them apart.</p>

<h3>Changing the geometry</h3>
<p>Edit <code>PLANES</code>. Each entry is two orthonormal basis vectors spanning the plane, plus a color. Keep <code>u</code> and <code>v</code> unit-length and perpendicular, or planes render sheared rather than square.</p>
<pre><code>{{"name": "record", "color": "#8B5CF6",
 "u": (0.7071, 0.0, -0.7071),
 "v": (0.4082, 0.8165, 0.4082)}}</code></pre>
<p>Global knobs: <code>HALF</code> (plane half-width), <code>AXIS</code> (axis half-length — how far the lines overhang the planes), <code>DIVISIONS</code> (default grid density).</p>

<h3>Verifying geometry after an edit</h3>
<p>Run this to confirm the basis vectors are still unit and perpendicular, and that the coordinate planes are still mutually orthogonal:</p>
<pre><code>python3 -c "
import itertools, math
from render_logo import PLANES
def cross(a,b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def norm(a): return math.sqrt(dot(a,a))
n={{}}
for p in PLANES:
    c=cross(p['u'],p['v']); L=norm(c); n[p['name']]=tuple(v/L for v in c)
    print(p['name'], norm(p['u']), norm(p['v']), dot(p['u'],p['v']))
for a,b in itertools.combinations(n,2):
    ang=math.degrees(math.acos(max(-1,min(1,abs(dot(n[a],n[b]))))))
    print(a, 'vs', b, round(ang,2))
"</code></pre>
<p>Expect lengths of 1.0, dot products of 0.0, 90.0° between each pair of coordinate planes, and ~54.74° between <code>record</code> and each of the other three.</p>

<h3>Checking small sizes after an edit</h3>
<pre><code>pip install cairosvg pillow
python3 -c "
import cairosvg
from PIL import Image
sizes=[16,24,32,48,64]
for s in sizes:
    cairosvg.svg2png(url='planes-small-on-light.svg', write_to='/tmp/t%d.png' % s,
                     output_width=s, output_height=s, background_color='white')
imgs=[Image.open('/tmp/t%d.png' % s).convert('RGB') for s in sizes]
t=[im.resize((im.width*8,im.height*8), Image.NEAREST) for im in imgs]
W=sum(i.width for i in t)+16*(len(t)+1); H=max(i.height for i in t)+32
sheet=Image.new('RGB',(W,H),'#dddddd'); x=16
for i in t:
    sheet.paste(i,(x,16)); x+=i.width+16
sheet.save('/tmp/contact_sheet.png')
"</code></pre>
<p>Then open <code>/tmp/contact_sheet.png</code> and look at it. Do not infer legibility from file size.</p>

<h2>Files</h2>
<table>
  <thead><tr><th>File</th><th>Role</th></tr></thead>
  <tbody>
    <tr><td><code>render_logo.py</code></td><td>Source of truth. Geometry, camera, emission, and this sheet's template.</td></tr>
    <tr><td><code>planes-{{view}}-on-{{ink}}.svg</code></td><td>Generated. Do not hand-edit — regenerate.</td></tr>
    <tr><td><code>planes-identity.html</code></td><td>Generated. This sheet, with specimens inlined.</td></tr>
    <tr><td><code>planes-icon-animated.html</code></td><td>Animated icon. Ink follows system light/dark.</td></tr>
  </tbody>
</table>

<div class="note">
<strong>Not done.</strong> The animated version is hand-written CSS and is <em>not</em> generated from <code>render_logo.py</code> — its geometry duplicates the script's by hand and can drift. Unifying them is open work.
</div>

<footer>
planes — visual identity master sheet. Rough marker; nothing locked. Regenerate everything with <code>python3 render_logo.py</code>.
</footer>

</div>
</body>
</html>
"""

def inline_svg(svg, px):
    """Strip the XML prolog and force a display size for embedding in HTML."""
    body = svg.strip()
    body = body.replace("<svg ", f'<svg width="{px}" height="{px}" ', 1)
    return body


# ---------------------------------------------------------------------------
# THE ANIMATED MARK (D-Q1, completing v7.0 §89)
# ---------------------------------------------------------------------------
# The animated icon was hand-written CSS whose geometry restated PLANES by
# hand — four `transform:` rules and a grid cell size, none of which the data
# above knew about. That duplication is the whole of D-Q1, and it had already
# drifted: the hand-written oblique plane was `rotateX(45deg) rotateY(45deg)`,
# which is not the basis `record` actually declares, and its grid was 8.5 cells
# to the SVGs' six. The static marks and the moving one disagreed.
#
# So the CSS comes from the same PLANES and VIEWS the SVGs come from. What is
# NOT derived is the motion — the 24s linear spin, the -18° tilt, the 800px
# perspective — because those are design decisions already made, and this is a
# unification, not a redesign.

PLANE_PX = 170.0        # the animated plane's on-screen side, as drawn before
WRAP_PX = 230.0         # the spinning box that contains it
STAGE_PX = 300.0        # the padded stage, so a corner never clips mid-spin


def cross3(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def css_basis(plane):
    """A plane's CSS 3D transform, from the basis the SVGs already use.

    An element lies in the screen's XY plane by default, so the transform is
    just the change of basis: local x -> u, local y -> v, local z -> u x v.
    `matrix3d` is column-major, and CSS's Y grows downward where the model's
    grows up, so every column is flipped in Y. That reflection is applied
    consistently to all three, which mirrors the frame and leaves the geometry
    exactly where the projection puts it.
    """
    u, v = plane["u"], plane["v"]
    n = cross3(u, v)
    cols = []
    for vec in (u, v, n):
        cols.append((vec[0], -vec[1], vec[2], 0.0))
    nums = [c for col in cols for c in col] + [0.0, 0.0, 0.0, 1.0]

    def m(v):
        # Four places, not two: these are direction cosines, and `fmt`'s two
        # would round 0.7071 to 0.71 — a fifth of a degree of skew per plane.
        # And -0.0 is 0.
        v = 0.0 if v == 0 else v
        return f"{v:.4f}".rstrip("0").rstrip(".")

    return "matrix3d(" + ", ".join(m(x) for x in nums) + ")"


ANIMATED_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>planes icon (animated)</title>
<!-- GENERATED by render_logo.py from PLANES/VIEWS — do not edit by hand.
     Regenerate with: python3 identity/render_logo.py -->
<style>
  html, body {{ margin: 0; height: 100%; display: flex; align-items: center; justify-content: center; background: transparent; }}
  :root {{ --ink: {ink_light}; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --ink: {ink_dark}; }} }}
  .stage {{ width: {stage}px; height: {stage}px; perspective: 800px; display: flex; align-items: center; justify-content: center; }}
  .wrap {{ position: relative; width: {wrap}px; height: {wrap}px; transform-style: preserve-3d; animation: spin 24s linear infinite; }}
  @keyframes spin {{ from {{ transform: rotateX(-18deg) rotateY(0deg); }} to {{ transform: rotateX(-18deg) rotateY(360deg); }} }}
  .plane {{ position: absolute; top: 50%; left: 50%; width: {plane}px; height: {plane}px; margin: {plane_off}px 0 0 {plane_off}px; background-size: {cell}px {cell}px; }}
{plane_rules}
  .axis {{ position: absolute; top: 50%; left: 50%; background: var(--ink); }}
  .ax {{ width: {axis}px; height: {axis_w}px; margin: {axis_wo}px 0 0 {axis_off}px; }}
  .ay {{ width: {axis_w}px; height: {axis}px; margin: {axis_off}px 0 0 {axis_wo}px; }}
  .az {{ width: {axis}px; height: {axis_w}px; margin: {axis_wo}px 0 0 {axis_off}px; transform: rotateY(90deg); }}
  .origin {{ position: absolute; top: 50%; left: 50%; width: {dot}px; height: {dot}px; margin: {dot_off}px 0 0 {dot_off}px; background: var(--ink); border-radius: 50%; }}
</style>
</head>
<body>
<div class="stage">
  <div class="wrap">
{plane_divs}
    <div class="axis ax"></div>
    <div class="axis ay"></div>
    <div class="axis az"></div>
    <div class="origin"></div>
  </div>
</div>
</body>
</html>
"""


def build_animated():
    """The animated mark, emitted from PLANES rather than restated in CSS."""
    view = VIEWS["hero"]
    divisions = view.get("divisions", DIVISIONS)
    cell = PLANE_PX / divisions
    axis_px = PLANE_PX * (AXIS / HALF)
    axis_w = view.get("axis_width", 2.0)
    dot = 2 * view.get("origin_r", 4.0) * (PLANE_PX / (2 * HALF))
    stroke = view.get("plane_stroke", 1.6)

    rules, divs = [], []
    for i, plane in enumerate(PLANES, 1):
        c = plane["color"]
        r, g, b = (int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16))
        rules.append(
            f'  .p{i} {{ background-image: linear-gradient(rgba({r},{g},{b},.5) 1px, transparent 1px), '
            f'linear-gradient(90deg, rgba({r},{g},{b},.5) 1px, transparent 1px); '
            f'border: {fmt(stroke)}px solid rgba({r},{g},{b},.85); '
            f'transform: {css_basis(plane)}; }}   /* {plane["name"]} */'
        )
        divs.append(f'    <div class="plane p{i}"></div>')

    html = ANIMATED_TEMPLATE.format(
        ink_light=INK_LIGHT.lower(), ink_dark=INK_DARK.lower(),
        stage=fmt(STAGE_PX), wrap=fmt(WRAP_PX),
        plane=fmt(PLANE_PX), plane_off=fmt(-PLANE_PX / 2), cell=fmt(cell),
        plane_rules="\n".join(rules), plane_divs="\n".join(divs),
        axis=fmt(axis_px), axis_w=fmt(axis_w), axis_wo=fmt(-axis_w / 2),
        axis_off=fmt(-axis_px / 2), dot=fmt(dot), dot_off=fmt(-dot / 2),
    )
    path = os.path.join(OUT_DIR, "planes-icon-animated.html")
    with open(path, "w") as fh:
        fh.write(html)
    return path


def build_sheet():
    """Emit the identity sheet with every specimen inlined, so it has no
    external file dependencies and renders correctly from any location."""
    specimens = {}
    for view_name, view in VIEWS.items():
        for ink_name, ink in (("light", INK_LIGHT), ("dark", INK_DARK)):
            svg = render(view["yaw"], view["pitch"], view["size"], ink, view)
            specimens[(view_name, ink_name)] = inline_svg(svg, 150)

    def row(ink_name):
        cells = []
        cap_color = "#8d8d8a" if ink_name == "dark" else "var(--muted)"
        for view_name in VIEWS:
            cells.append(
                f'<div><div class="spec">{specimens[(view_name, ink_name)]}</div>'
                f'<div class="cap" style="color:{cap_color}">{view_name} · on {ink_name}</div></div>'
            )
        return "\n".join(cells)

    swatches = "\n".join(
        f'  <div class="swatch-row"><span class="chip" style="background:{p["color"]}"></span>'
        f'<span class="swatch-meta">{p["name"]}<br><span class="hex">{p["color"]}</span>'
        f'{" · the oblique plane" if p["name"] == "record" else ""}</span></div>'
        for p in PLANES
    )

    html = SHEET_TEMPLATE.format(
        swatches=swatches,
        light_row=row("light"),
        dark_row=row("dark"),
    )
    path = os.path.join(OUT_DIR, "planes-identity.html")
    with open(path, "w") as fh:
        fh.write(html)
    return path


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    written = []
    for view_name, view in VIEWS.items():
        for ink_name, ink in (("light", INK_LIGHT), ("dark", INK_DARK)):
            svg = render(view["yaw"], view["pitch"], view["size"], ink, view)
            path = os.path.join(OUT_DIR, f"planes-{view_name}-on-{ink_name}.svg")
            with open(path, "w") as fh:
                fh.write(svg)
            written.append(path)
    written.append(build_animated())
    written.append(build_sheet())
    for path in written:
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
