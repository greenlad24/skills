#!/usr/bin/env python3
"""Generate manifest.ttl + <name>.ttl for a VibeNation Faust plugin from `faust -json` output.

Port order must match common/vn_arch.cpp: audio ins, audio outs, UI widgets
(depth-first, declaration order), then a 'latency' output port.

Widget label = LV2 symbol. Widget metadata understood:
  [name:Peak Reduction]  human-readable port name
  [unit:dB|ms|s|Hz|%|pc] lv2 units
  [enum:A|B|C]           integer enumeration with scale points 0..n-1
  [integer]              integer port
  [log]                  logarithmic port
Program metadata: declare vn_name, vn_class (lv2 class, e.g. CompressorPlugin), vn_comment.
"""
import json, sys, os

URI_BASE = "https://vibenation.app/lv2/"
UNITS = {"dB": "units:db", "ms": "units:ms", "s": "units:s", "Hz": "units:hz",
         "%": "units:pc", "pc": "units:pc", "x": "units:coef"}


def widgets(items):
    for it in items:
        if it["type"] in ("vgroup", "hgroup", "tgroup"):
            yield from widgets(it["items"])
        else:
            yield it


def meta_dict(lst):
    d = {}
    for m in lst or []:
        d.update(m)
    return d


def esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


def num(v):
    return repr(float(v))


def main(json_path, outdir, name):
    j = json.load(open(json_path))
    gmeta = meta_dict(j.get("meta"))
    uri = URI_BASE + name
    nin, nout = int(j["inputs"]), int(j["outputs"])
    cls = gmeta.get("vn_class", "Plugin")
    pname = gmeta.get("vn_name", name)
    comment = gmeta.get("vn_comment", gmeta.get("description", ""))

    ports = []
    idx = 0
    in_names = ["in"] if nin == 1 else ["in_l", "in_r"]
    out_names = ["out"] if nout == 1 else ["out_l", "out_r"]
    for i in range(nin):
        ports.append(f"""        a lv2:AudioPort , lv2:InputPort ;
        lv2:index {idx} ;
        lv2:symbol "{in_names[i]}" ;
        lv2:name "{'Input' if nin == 1 else ('Input L', 'Input R')[i]}" """)
        idx += 1
    for i in range(nout):
        ports.append(f"""        a lv2:AudioPort , lv2:OutputPort ;
        lv2:index {idx} ;
        lv2:symbol "{out_names[i]}" ;
        lv2:name "{'Output' if nout == 1 else ('Output L', 'Output R')[i]}" """)
        idx += 1

    seen = set()
    for w in widgets(j["ui"]):
        m = meta_dict(w.get("meta"))
        sym = w["label"]
        if sym in seen or not sym.replace("_", "").isalnum() or sym[0].isdigit():
            raise SystemExit(f"bad/duplicate symbol {sym!r} in {name}")
        seen.add(sym)
        is_out = w["type"] in ("hbargraph", "vbargraph")
        lo, hi = float(w.get("min", 0)), float(w.get("max", 1))
        lines = [f"        a lv2:ControlPort , {'lv2:OutputPort' if is_out else 'lv2:InputPort'} ;",
                 f"        lv2:index {idx} ;",
                 f'        lv2:symbol "{sym}" ;',
                 f'        lv2:name "{esc(m.get("name", sym))}" ;',
                 f"        lv2:minimum {num(lo)} ;",
                 f"        lv2:maximum {num(hi)} ;"]
        if not is_out:
            init = float(w.get("init", 0)) if w["type"] not in ("checkbox", "button") else 0.0
            if "vn_default" in m:
                init = float(m["vn_default"])
            lines.append(f"        lv2:default {num(init)} ;")
        else:
            lines.append(f"        lv2:default {num(0.0)} ;")
        props = []
        if w["type"] in ("checkbox", "button"):
            props.append("lv2:toggled")
        if "enum" in m:
            props += ["lv2:integer", "lv2:enumeration"]
            pts = m["enum"].split("|")
            sp = " , ".join(f'[ rdfs:label "{esc(lbl)}" ; rdf:value {num(k)} ]' for k, lbl in enumerate(pts))
            lines.append(f"        lv2:scalePoint {sp} ;")
        elif "integer" in m:
            props.append("lv2:integer")
        if "log" in m:
            props.append("pprops:logarithmic")
        if props:
            lines.append("        lv2:portProperty " + " , ".join(props) + " ;")
        if m.get("unit") in UNITS:
            lines.append(f"        units:unit {UNITS[m['unit']]} ;")
        ports.append("\n".join(lines).rstrip(" ;"))
        idx += 1

    ports.append(f"""        a lv2:ControlPort , lv2:OutputPort ;
        lv2:index {idx} ;
        lv2:symbol "latency" ;
        lv2:name "Latency" ;
        lv2:minimum 0.0 ;
        lv2:maximum 64.0 ;
        lv2:default 0.0 ;
        lv2:designation lv2:latency ;
        lv2:portProperty lv2:reportsLatency , lv2:integer ;
        units:unit units:frame""")

    body = "\n    ] , [\n".join(ports)
    ttl = f"""@prefix doap:   <http://usefulinc.com/ns/doap#> .
@prefix foaf:   <http://xmlns.com/foaf/0.1/> .
@prefix lv2:    <http://lv2plug.in/ns/lv2core#> .
@prefix pprops: <http://lv2plug.in/ns/ext/port-props#> .
@prefix rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs:   <http://www.w3.org/2000/01/rdf-schema#> .
@prefix units:  <http://lv2plug.in/ns/extensions/units#> .

<{uri}>
    a lv2:Plugin , lv2:{cls} ;
    doap:name "{esc(pname)}" ;
    doap:license <http://opensource.org/licenses/MIT> ;
    doap:maintainer [ foaf:name "VibeNation" ; foaf:homepage <https://vibenation.app/> ] ;
    rdfs:comment "{esc(comment)}" ;
    lv2:optionalFeature lv2:hardRTCapable ;
    lv2:minorVersion 0 ;
    lv2:microVersion 1 ;
    lv2:port [
{body}
    ] .
"""
    manifest = f"""@prefix lv2:  <http://lv2plug.in/ns/lv2core#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

<{uri}>
    a lv2:Plugin ;
    lv2:binary <{name}.so> ;
    rdfs:seeAlso <{name}.ttl> .
"""
    os.makedirs(outdir, exist_ok=True)
    open(os.path.join(outdir, f"{name}.ttl"), "w").write(ttl)
    open(os.path.join(outdir, "manifest.ttl"), "w").write(manifest)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
