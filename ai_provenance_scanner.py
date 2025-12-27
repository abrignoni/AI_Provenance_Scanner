#!/usr/bin/env python3

import argparse
import json
import mimetypes
from pathlib import Path
from exiftool import ExifToolHelper
from c2pa import Reader

try:
    import magic
    HAS_MAGIC = True
except ImportError:
    HAS_MAGIC = False

# ================================
# MIME DETECTION
# ================================
def detect_mime_type(file_path: Path):
    if HAS_MAGIC:
        try:
            return magic.from_file(str(file_path), mime=True)
        except Exception:
            pass
    mime, _ = mimetypes.guess_type(str(file_path))
    return mime

# ================================
# EXIFTOOL: FULL IPTC + JUMBF
# ================================
IPTC_TAG_PREFIXES = [
    "IPTC:", "IPTC-IIM:", "XMP-iptc:", "XMP-iptcExt:", "IPTC-dlgsrc:",
    "digsrctype:", "Iptc4xmpExt:", "photoshop:", "Credit",
    "Digital Source Type", "DigitalSourceType", "Profile Copyright"
]

def extract_iptc_and_jumbf(file_path: Path):
    result = {"iptc": {}, "jumbf_raw": {}, "exiftool_warnings": []}
    try:
        with ExifToolHelper(
            common_args=["-m", "-ignoreMinorErrors", "-api", "LargeFileSupport=1"]
        ) as et:
            all_data = et.get_metadata(str(file_path))
            for data in all_data:
                for tag, value in data.items():
                    if any(tag.startswith(p) for p in IPTC_TAG_PREFIXES):
                        result["iptc"][tag] = value
                    elif tag.startswith("JUMBF:"):
                        result["jumbf_raw"][tag] = value
    except Exception as e:
        result["exiftool_warnings"].append(str(e))
    return result

# ================================
# IPTC NORMALIZATION
# ================================
IPTC_MAP = {
    "creator": ["IPTC:By-line", "XMP-dc:Creator", "XMP-iptc:Creator"],
    "credit_line": ["IPTC:Credit", "XMP-photoshop:Credit", "photoshop:Credit", "Credit"],
    "copyright_notice": ["IPTC:CopyrightNotice", "XMP-dc:Rights"],
    "profile_copyright": ["Profile Copyright"],
    "description": ["IPTC:Caption-Abstract", "XMP-dc:Description"],
    "digital_source_type": [
        "XMP-iptcExt:DigitalSourceType",
        "IPTC-dlgsrc:DigitalSourceType",
        "digsrctype:compositeWithTrainedAlgorithmicMedia",
        "Iptc4xmpExt:DigitalSourceType",
        "Digital Source Type",
        "DigitalSourceType"
    ],
    "trained_algorithmic_media": ["IPTC-dlgsrc:trainedAlgorithmicMedia"],
    "digital_art": ["IPTC-dlgsrc:digitalArt"],
    "usage_terms": ["XMP-xmpRights:UsageTerms"]
}

def normalize_iptc_flat(raw):
    normalized = {}
    sources = {}
    def recursive_search(d):
        if isinstance(d, dict):
            for k, v in d.items():
                for field, tags in IPTC_MAP.items():
                    if k in tags and field not in normalized:
                        normalized[field] = v
                        sources[field] = k
                recursive_search(v)
        elif isinstance(d, list):
            for item in d:
                recursive_search(item)
    recursive_search(raw)
    dst = normalized.get("digital_source_type")
    normalized["ai_generated"] = dst.lower() not in ("originalphotograph","digitalcapture") if isinstance(dst, str) else None
    return normalized, sources

# ================================
# C2PA EXTRACTION
# ================================
def extract_c2pa(file_path: Path, report: dict):
    mime_type = detect_mime_type(file_path)
    report["mime_type"] = mime_type
    if not mime_type:
        return None
    try:
        with open(file_path, "rb") as file:
            reader = Reader(mime_type, file)
            data = reader.json()
            if not data:
                return None
            if isinstance(data, str):
                return json.loads(data)
            return data
    except Exception as e:
        report["c2pa_error"] = str(e)
        return None

# ================================
# C2PA NORMALIZATION (FLATTENED)
# ================================
AI_KEYS = {"digital_source_type", "trainedAlgorithmicMedia", "digitalArt", "compositeSynthetic", "virtualRecording"}

def flatten_dict(d, parent_key="", sep="."):
    items = {}
    if isinstance(d, dict):
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.update(flatten_dict(v, new_key, sep=sep))
            elif isinstance(v, list):
                for idx, item in enumerate(v):
                    list_key = f"{new_key}[{idx}]"
                    if isinstance(item, (dict, list)):
                        items.update(flatten_dict(item, list_key, sep=sep))
                    else:
                        items[list_key] = item
            else:
                items[new_key] = v
    return items

def normalize_c2pa_flat(c2pa_json):
    facts = {
        "signed": False,
        "actions": set(),
        "generator": None,
        "issuer": None,
        "common_name": None,
        "claim_generator": None,
        "trainedAlgorithmicMedia": None,
        "compositeSynthetic": None,
        "digitalArt": None,
        "virtualRecording": None,
        "credential_date": None,
        "flattened_manifest": {}
    }
    if not c2pa_json:
        return facts
    facts["signed"] = True
    def recursive_search(d):
        if isinstance(d, dict):
            for k, v in d.items():
                lk = k.lower()
                if lk == "issuer" and not facts["issuer"]:
                    facts["issuer"] = v
                elif lk == "common_name" and not facts["common_name"]:
                    facts["common_name"] = v
                elif lk == "claim_generator" and not facts["claim_generator"]:
                    facts["claim_generator"] = v
                elif lk.endswith("generator") and not facts["generator"]:
                    facts["generator"] = v
                elif lk == "actions" and isinstance(v, list):
                    for a in v:
                        if isinstance(a, str):
                            facts["actions"].add(a)
                elif k == "trainedAlgorithmicMedia" and not facts["trainedAlgorithmicMedia"]:
                    facts["trainedAlgorithmicMedia"] = v
                elif k == "compositeSynthetic" and not facts["compositeSynthetic"]:
                    facts["compositeSynthetic"] = v
                elif k == "digitalArt" and not facts["digitalArt"]:
                    facts["digitalArt"] = v
                elif k == "virtualRecording" and not facts["virtualRecording"]:
                    facts["virtualRecording"] = v
                elif k.lower() in ["time", "signed_date"] and not facts["credential_date"]:
                    facts["credential_date"] = v
                recursive_search(v)
        elif isinstance(d, list):
            for item in d:
                recursive_search(item)
    manifests = c2pa_json.get("manifests", {})
    if isinstance(manifests, dict):
        for manifest in manifests.values():
            facts["flattened_manifest"].update(flatten_dict(manifest))
            recursive_search(manifest)
    facts["actions"] = list(facts["actions"])
    return facts

# ================================
# FILE SCANNER
# ================================
def scan_file(path: Path, c2pa_only=False):
    report = {"file": str(path), "c2pa_present": False}
    c2pa_data = extract_c2pa(path, report)
    if c2pa_data:
        report["c2pa_present"] = True
        report["c2pa_raw"] = c2pa_data
    if not c2pa_only:
        meta = extract_iptc_and_jumbf(path)
        report.update(meta)
        iptc_norm, iptc_sources = normalize_iptc_flat(meta.get("iptc", {}))
        c2pa_norm = normalize_c2pa_flat(c2pa_data)
        report["analysis"] = {
            "iptc_normalized": iptc_norm,
            "iptc_sources_mapping": iptc_sources,
            "c2pa_normalized": c2pa_norm
        }
    return report

# ================================
# CONVERT SETS TO LISTS
# ================================
def convert_sets_to_lists(obj):
    if isinstance(obj, dict):
        return {k: convert_sets_to_lists(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_sets_to_lists(v) for v in obj]
    elif isinstance(obj, set):
        return list(obj)
    else:
        return obj

# ================================
# PAPER-FRIENDLY REPORT WITH AI HIGHLIGHT
# ================================
def print_paper_report(report, show_flattened=False):
    print("="*80)
    print(f"FILE: {report['file']}")
    print(f"MIME type: {report.get('mime_type','unknown')}")
    print(f"C2PA present: {report['c2pa_present']}")
    print("="*80)

    if 'analysis' in report:
        iptc = report['analysis']['iptc_normalized']
        iptc_sources = report['analysis']['iptc_sources_mapping']
        c2pa = report['analysis']['c2pa_normalized']

        print("\n--- IPTC Normalized ---")
        for k,v in iptc.items():
            src = iptc_sources.get(k,'unknown')
            ai_flag = " [AI GENERATED]" if (k in AI_KEYS and iptc.get("ai_generated")) else ""
            val_str = str(v)
            if len(val_str) > 150:
                val_str = val_str[:150] + " ... [truncated]"
            print(f"{k.replace('_',' ').title():30}: {val_str} (raw tag: {src}){ai_flag}")

        print("\n--- C2PA Normalized ---")
        ai_flag_c2pa = " [AI GENERATED]" if "generate" in c2pa.get('actions', []) else ""
        for key, value in c2pa.items():
            if key not in ["actions", "flattened_manifest"]:
                highlight = " [AI GENERATED]" if key in AI_KEYS and value else ""
                val_str = str(value)
                if len(val_str) > 150:
                    val_str = val_str[:150] + " ... [truncated]"
                print(f"{key.replace('_',' ').title():30}: {val_str}{highlight}")
        actions_str = ', '.join(c2pa.get('actions', [])) if c2pa.get('actions') else 'None'
        print(f"{'Actions':30}: {actions_str}{ai_flag_c2pa}")

        # Flattened manifest only if --flattened provided
        if show_flattened:
            print("\n--- Flattened C2PA Manifest ---")
            for k, v in c2pa.get("flattened_manifest", {}).items():
                highlight = ""
                for ai_key in AI_KEYS:
                    if ai_key.lower() in k.lower():
                        highlight = " [AI GENERATED]"
                        break
                if isinstance(v, str) and "generate" in v.lower():
                    highlight = " [AI GENERATED]"
                val_str = str(v)
                if len(val_str) > 150:
                    val_str = val_str[:150] + " ... [truncated]"
                print(f"{k:60}: {val_str}{highlight}")

    if report.get('exiftool_warnings'):
        print("\n--- ExifTool Warnings ---")
        for w in report['exiftool_warnings']:
            print(f"- {w}")
    print("\n\n")

# ================================
# CLI
# ================================
def main():
    parser = argparse.ArgumentParser(description="AI provenance scanner (C2PA + IPTC + JUMBF + analysis)")
    parser.add_argument("--path", required=True, help="File or directory to scan")
    parser.add_argument("--json", action="store_true", help="Output full JSON")
    parser.add_argument("--c2pa-only", action="store_true", help="Only extract C2PA")
    parser.add_argument("--flattened", action="store_true", help="Show flattened C2PA manifest in report")
    args = parser.parse_args()

    target = Path(args.path)
    results = []

    if target.is_file():
        results.append(scan_file(target, args.c2pa_only))
    elif target.is_dir():
        for f in target.iterdir():
            if f.is_file():
                results.append(scan_file(f, args.c2pa_only))
    else:
        raise ValueError("Invalid path")

    if args.json:
        serializable_results = convert_sets_to_lists(results)
        print(json.dumps(serializable_results, indent=2))
    else:
        for r in results:
            print_paper_report(r, show_flattened=args.flattened)

if __name__ == "__main__":
    main()
