import os
import re
import json
from typing import Dict, Any, List

from flask import Flask, request, jsonify
from flask_cors import CORS
import httpx
from dotenv import load_dotenv

# Optional: Gemini integration
try:
    import google.generativeai as genai  # type: ignore
except Exception:
    genai = None

load_dotenv()

app = Flask(__name__)
CORS(app)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
# Use classic endpoints for legacy APIs
CLINICAL_TRIALS_STUDY_FIELDS = "https://classic.clinicaltrials.gov/api/query/study_fields"
CLINICAL_TRIALS_FULL_STUDIES = "https://classic.clinicaltrials.gov/api/query/full_studies"
CLINICAL_TRIALS_V2_STUDIES = "https://clinicaltrials.gov/api/v2/studies"

# ---------- Utilities ----------

def _extract_age_from_text(text: str) -> tuple[int | None, bool]:
    """Find age using multiple patterns; return (age, specific_found).
    specific_found is True when pattern is 'X-year-old' or 'aged X', which is more reliable
    than generic 'X years' that can refer to durations.
    """
    lower = text.lower()
    matches: list[tuple[int, int, bool]] = []  # (start_index, age, is_specific)
    # Specific forms first: '68-year-old', 'aged 68'
    for m in re.finditer(r"\b(\d{1,3})\s*[- ]?(?:year|yr)s?[- ]?old\b", lower):
        try:
            matches.append((m.start(), int(m.group(1)), True))
        except Exception:
            pass
    for m in re.finditer(r"\baged\s*(\d{1,3})\b", lower):
        try:
            matches.append((m.start(), int(m.group(1)), True))
        except Exception:
            pass
    # Generic forms: '58 years', '58 yo', '58 y/o'
    for m in re.finditer(r"\b(\d{1,3})\s*(?:years?|yo|y/o)\b", lower):
        try:
            matches.append((m.start(), int(m.group(1)), False))
        except Exception:
            pass
    if not matches:
        return (None, False)
    # Choose earliest occurrence; if tie, prefer specific=True
    matches.sort(key=lambda t: (t[0], 0 if t[2] else 1))
    _, age, is_specific = matches[0]
    if age < 0 or age > 120:
        return (None, is_specific)
    return (age, is_specific)


def _regex_extract(text: str) -> Dict[str, Any]:
    """Very simple heuristic extractor as a safe fallback when no LLM key is set."""
    lower = text.lower()
    # Find age robustly
    age_val, _ = _extract_age_from_text(text)
    sex_match = re.search(r"\b(male|female|man|woman)\b", lower)
    dx_match = re.search(r"diagnos(?:is|ed)\s*(?:with)?\s*([\w\s\-]+?)(?:\.|,|;|$)", lower)

    def norm_sex(s: str | None) -> str | None:
        if not s:
            return None
        if s in ["male", "man"]:
            return "Male"
        if s in ["female", "woman"]:
            return "Female"
        return None

    age = age_val
    sex = norm_sex(sex_match.group(1) if sex_match else None)
    diagnosis = dx_match.group(1).strip().title() if dx_match else None
    if not diagnosis:
        # Cardiology patterns
        if "heart failure" in lower:
            if "reduced ejection fraction" in lower or re.search(r"\bhfref\b", lower):
                diagnosis = "Heart failure with reduced ejection fraction (HFrEF)"
            else:
                diagnosis = "Heart failure"

    # simple keyword harvesting
    keywords = []
    for kw in [
        "stage ii", "stage iii", "metastatic", "recurrent", "adjuvant",
        "neoadjuvant", "immunotherapy", "chemo", "radiation", "biomarker",
        "egfr", "alk", "brca", "pd-l1", "her2",
        # Cardiology
        "heart failure", "hfrEF", "reduced ejection fraction", "nyha", "sglt2"
    ]:
        if kw in lower:
            keywords.append(kw)

    locations = []
    for m in re.finditer(r"\b(in|at)\s+([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)*)\b", text):
        loc = m.group(2)
        if loc not in locations and len(loc) > 2:
            locations.append(loc)

    return {
        "age": age,
        "sex": sex,
        "diagnosis": diagnosis,
        "keywords": keywords,
        "locations": locations[:3],
    }

def _gemini_extract(transcript: str) -> Dict[str, Any]:
    if not GOOGLE_API_KEY or genai is None:
        
        return _regex_extract(transcript)
    genai.configure(api_key=GOOGLE_API_KEY)
    # Use a compact, deterministic prompt and require strict JSON output
    prompt = (
        "You are extracting structured clinical info from a patient-doctor transcript.\n"
        "Requirements:\n"
        "- Output ONLY JSON (no prose).\n"
        "- Keys: age (number or null), sex ('Male'|'Female'|null), diagnosis (string or null), keywords (string[]), locations (string[]).\n"
        "- Age must be the patient's current age, not durations (e.g., 'quit 10 years ago' is NOT age).\n"
        "- Prefer concise, canonical diagnosis terms (e.g., 'Heart failure with reduced ejection fraction (HFrEF)', 'HER2-positive invasive ductal carcinoma').\n"
        "- Keywords: include staging, biomarkers, therapies (e.g., HER2, HFrEF, NYHA, SGLT2, adjuvant).\n"
        "Transcript:\n\n" + transcript
    )
    try:
        # Try configured model first, then fallbacks for compatibility
        candidate_models = [GEMINI_MODEL,
                            "gemini-2.5-flash",
                            "gemini-2.5-flash-latest",
                            "gemini-1.5-flash-latest",
                            "gemini-1.5-pro-latest",
                            "gemini-1.5-flash",
                            "gemini-1.5-pro"]
        last_exc = None
        for mid in candidate_models:
            try:
                model = genai.GenerativeModel(mid)
                resp = model.generate_content(prompt, generation_config={
                    "temperature": 0.2,
                    "top_p": 0.9,
                })
                break
            except Exception as e_model:
                last_exc = e_model
                continue
        else:
            raise last_exc or RuntimeError("No Gemini model succeeded")
        text = resp.text.strip()
        # Try to locate JSON in response
        json_str = text
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            json_str = m.group(0)
        data = json.loads(json_str)
        # basic normalization
        if isinstance(data.get("sex"), str):
            s = data["sex"].lower()
            data["sex"] = "Male" if "male" in s else ("Female" if "female" in s else None)
        # normalize age if string like '58-year-old'
        if isinstance(data.get("age"), str):
            m_age = re.search(r"\b(\d{1,3})\b", data["age"])  # extract first integer
            if m_age:
                try:
                    data["age"] = int(m_age.group(1))
                except Exception:
                    data["age"] = None
        # sanity bound age
        if isinstance(data.get("age"), int) and (data["age"] < 0 or data["age"] > 120):
            data["age"] = None
        # If LLM age is missing, fall back to textual age
        txt_age, _ = _extract_age_from_text(transcript)
        if txt_age is not None and data.get("age") is None:
            data["age"] = txt_age
            
        return {
            "age": data.get("age"),
            "sex": data.get("sex"),
            "diagnosis": data.get("diagnosis"),
            "keywords": data.get("keywords", [])[:10],
            "locations": data.get("locations", [])[:5],
        }
    except Exception as e:
        
        return _regex_extract(transcript)


def build_expr(extracted: Dict[str, Any]) -> str:
    parts: List[str] = []
    dx = (extracted.get("diagnosis") or "").lower()
    kws = [k.lower() for k in (extracted.get("keywords") or [])]

    def add(term: str):
        if term and term not in parts:
            parts.append(term)

    # Expand diagnosis for common synonyms
    if "breast" in dx or "ductal" in dx:
        add('"breast cancer"')
        add('"invasive ductal carcinoma"')
    if "her2" in dx or any("her2" in k for k in kws):
        add('"HER2 positive"')
        add('HER2')
    # Heart failure expansions
    if "heart failure" in dx or any("heart failure" in k for k in kws):
        add('"heart failure"')
    if "hfr" in dx or any("hfr" in k for k in kws) or any("reduced ejection fraction" in k for k in kws):
        add('HFrEF')
        add('"reduced ejection fraction"')
    if not parts and dx:
        # Quote multi-word diagnosis
        if len(dx.split()) > 1:
            add(f'"{dx}"')
        else:
            add(dx)

    # Add a few keywords (quoted if multi-word), prefer therapeutic intents
    priors = []
    for kw in kws:
        if kw in priors:
            continue
        priors.append(kw)
        if len(priors) > 5:
            break
        add(f'"{kw}"' if ' ' in kw else kw)

    # Fallback generic anchors
    if not parts:
        parts = ['"breast cancer"', 'HER2']

    # Compose with OR to avoid overly restrictive AND
    return " OR ".join(parts)


def age_in_range(age: int | None, min_age: str | None, max_age: str | None) -> bool:
    if age is None:
        return True
    def to_years(s: str | None) -> int | None:
        if not s:
            return None
        s = s.lower()
        if s in ("n/a", "none", ""):
            return None
        m = re.match(r"(\d+)\s*(year|years|month|months|day|days)?", s)
        if not m:
            return None
        val = int(m.group(1))
        unit = m.group(2) or "years"
        if unit.startswith("year"):
            return val
        if unit.startswith("month"):
            return max(0, val // 12)
        if unit.startswith("day"):
            return max(0, val // 365)
        return val
    miny = to_years(min_age)
    maxy = to_years(max_age)
    if miny is not None and age < miny:
        return False
    if maxy is not None and age > maxy:
        return False
    return True


def sex_matches(sex: str | None, trial_gender: str | None) -> bool:
    if sex is None or not trial_gender:
        return True
    tg = trial_gender.lower()
    if tg == "all":
        return True
    if sex == "Male" and tg == "male":
        return True
    if sex == "Female" and tg == "female":
        return True
    return False


def query_trials(extracted: Dict[str, Any], max_rows: int = 30) -> Dict[str, Any]:
    expr = build_expr(extracted)
    fields = [
        "NCTId","BriefTitle","Condition","OverallStatus","BriefSummary",
        "LocationCity","LocationState","LocationCountry","Gender",
        "MinimumAge","MaximumAge","Phase","StudyType","InterventionName",
        "DetailedDescription","EligibilityCriteria"
    ]
    params = {
        "expr": expr,
        "fields": ",".join(fields),
        "min_rnk": 1,
        "max_rnk": max_rows,
        "fmt": "json",
    }
    headers = {"User-Agent": "DeepScribeTrialsDemo/0.1 (+https://example.com)"}
    try:
        with httpx.Client(timeout=20, headers=headers) as client:
            r = client.get(CLINICAL_TRIALS_STUDY_FIELDS, params=params)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as e:
        # Fallback: try full_studies and map a subset of fields
        try:
            with httpx.Client(timeout=20, headers=headers) as client:
                r2 = client.get(CLINICAL_TRIALS_FULL_STUDIES, params={
                    "expr": expr,
                    "min_rnk": 1,
                    "max_rnk": max_rows,
                    "fmt": "json",
                })
                r2.raise_for_status()
                data2 = r2.json()
            studies = data2.get("FullStudiesResponse", {}).get("FullStudies", [])
            mapped = []
            for item in studies:
                study = (item or {}).get("Study", {})
                proto = study.get("ProtocolSection", {})
                id_module = proto.get("IdentificationModule", {})
                desc_module = proto.get("DescriptionModule", {})
                status_module = proto.get("StatusModule", {})
                design_module = proto.get("DesignModule", {})
                eligibility = proto.get("EligibilityModule", {})
                contacts = proto.get("ContactsLocationsModule", {})
                interventions = proto.get("ArmsInterventionsModule", {}) or proto.get("InterventionsModule", {})

                nct_id = id_module.get("NCTId")
                title = id_module.get("BriefTitle") or study.get("ProtocolSection", {}).get("IdentificationModule", {}).get("OfficialTitle")
                conditions = proto.get("ConditionsModule", {}).get("ConditionList", {}).get("Condition", [])
                overall_status = status_module.get("OverallStatus")
                brief_summary = desc_module.get("BriefSummary") or ""
                phase_val = design_module.get("PhaseList", {}).get("Phase")
                if isinstance(phase_val, list):
                    phase_list = phase_val
                elif phase_val:
                    phase_list = [phase_val]
                else:
                    phase_list = []
                study_type = design_module.get("StudyType")
                gender = (eligibility.get("Gender") or "All")
                min_age = eligibility.get("MinimumAge") or "N/A"
                max_age = eligibility.get("MaximumAge") or "N/A"

                # locations
                locs = (contacts.get("LocationList", {}) or {}).get("Location", [])
                loc_city, loc_state, loc_country = [], [], []
                for loc in locs:
                    fac = (loc or {}).get("Facility", {})
                    l = fac.get("Location", {})
                    if l.get("City"): loc_city.append(l.get("City"))
                    if l.get("State"): loc_state.append(l.get("State"))
                    if l.get("Country"): loc_country.append(l.get("Country"))

                # interventions
                names = []
                if interventions:
                    # try InterventionsModule.InterventionList.Intervention[].InterventionName
                    im = proto.get("InterventionsModule", {})
                    ilist = (im.get("InterventionList", {}) or {}).get("Intervention", [])
                    for iv in ilist:
                        nm = iv.get("InterventionName")
                        if nm: names.append(nm)
                mapped.append({
                    "NCTId": [nct_id] if nct_id else [],
                    "BriefTitle": [title] if title else [],
                    "Condition": conditions or [],
                    "OverallStatus": [overall_status] if overall_status else [],
                    "BriefSummary": [brief_summary],
                    "LocationCity": loc_city,
                    "LocationState": loc_state,
                    "LocationCountry": loc_country,
                    "Gender": [gender] if gender else [],
                    "MinimumAge": [min_age] if min_age else [],
                    "MaximumAge": [max_age] if max_age else [],
                    "Phase": phase_list,
                    "StudyType": [study_type] if study_type else [],
                    "InterventionName": names,
                    "DetailedDescription": [],
                    "EligibilityCriteria": [],
                })
            # Apply same local filters
            age = extracted.get("age")
            sex = extracted.get("sex")
            filtered = []
            for s in mapped:
                gender = (s.get("Gender") or [None])[0]
                min_age = (s.get("MinimumAge") or [None])[0]
                max_age = (s.get("MaximumAge") or [None])[0]
                if not age_in_range(age, min_age, max_age):
                    continue
                if not sex_matches(sex, gender):
                    continue
                filtered.append(s)
            return {"expr": expr, "count": len(filtered), "studies": filtered[:15], "endpoint": CLINICAL_TRIALS_FULL_STUDIES}
        except httpx.HTTPError as e2:
            # Second fallback: v2 API
            try:
                with httpx.Client(timeout=20, headers=headers) as client:
                    r3 = client.get(CLINICAL_TRIALS_V2_STUDIES, params={
                        "query.term": expr,
                        "pageSize": max_rows,
                    })
                    r3.raise_for_status()
                    data3 = r3.json()
                studies_v2 = data3.get("studies", [])
                mapped_v2 = []
                for s in studies_v2:
                    proto = (s or {}).get("protocolSection", {})
                    idm = proto.get("identificationModule", {})
                    desc = proto.get("descriptionModule", {})
                    status = proto.get("statusModule", {})
                    design = proto.get("designModule", {})
                    elig = proto.get("eligibilityModule", {})
                    contacts = proto.get("contactsLocationsModule", {})
                    imods = proto.get("interventionsModule", {})

                    nct_id = idm.get("nctId")
                    title = idm.get("briefTitle") or idm.get("officialTitle")
                    conditions = (proto.get("conditionsModule", {}) or {}).get("conditions", [])
                    overall_status = status.get("overallStatus")
                    brief_summary = desc.get("briefSummary") or ""
                    phase_list = design.get("phases") or []
                    study_type = design.get("studyType")
                    gender = elig.get("sex") or "All"
                    min_age = elig.get("minimumAge") or "N/A"
                    max_age = elig.get("maximumAge") or "N/A"

                    # locations
                    locs = (contacts.get("locations") or [])
                    loc_city, loc_state, loc_country = [], [], []
                    for loc in locs:
                        l = loc.get("location") or {}
                        if l.get("city"): loc_city.append(l.get("city"))
                        if l.get("state"): loc_state.append(l.get("state"))
                        if l.get("country"): loc_country.append(l.get("country"))

                    # interventions
                    names = []
                    ivs = (imods.get("interventions") or [])
                    for iv in ivs:
                        nm = iv.get("name")
                        if nm: names.append(nm)

                    mapped_v2.append({
                        "NCTId": [nct_id] if nct_id else [],
                        "BriefTitle": [title] if title else [],
                        "Condition": conditions or [],
                        "OverallStatus": [overall_status] if overall_status else [],
                        "BriefSummary": [brief_summary],
                        "LocationCity": loc_city,
                        "LocationState": loc_state,
                        "LocationCountry": loc_country,
                        "Gender": [gender] if gender else [],
                        "MinimumAge": [min_age] if min_age else [],
                        "MaximumAge": [max_age] if max_age else [],
                        "Phase": phase_list,
                        "StudyType": [study_type] if study_type else [],
                        "InterventionName": names,
                        "DetailedDescription": [],
                        "EligibilityCriteria": [],
                    })

                # Apply same filters
                age = extracted.get("age")
                sex = extracted.get("sex")
                filtered = []
                for s in mapped_v2:
                    gender = (s.get("Gender") or [None])[0]
                    min_age = (s.get("MinimumAge") or [None])[0]
                    max_age = (s.get("MaximumAge") or [None])[0]
                    if not age_in_range(age, min_age, max_age):
                        continue
                    if not sex_matches(sex, gender):
                        continue
                    filtered.append(s)

                return {"expr": expr, "count": len(filtered), "studies": filtered[:15], "endpoint": CLINICAL_TRIALS_V2_STUDIES}
            except httpx.HTTPError as e3:
                return {
                    "expr": expr,
                    "count": 0,
                    "studies": [],
                    "error": f"study_fields error: {str(e)}; full_studies error: {str(e2)}; v2 error: {str(e3)}",
                    "endpoint": CLINICAL_TRIALS_V2_STUDIES,
                }
    studies = data.get("StudyFieldsResponse", {}).get("StudyFields", [])

    # local filtering based on age and sex
    age = extracted.get("age")
    sex = extracted.get("sex")
    filtered = []
    for s in studies:
        # each field returns list values from API
        gender = (s.get("Gender") or [None])[0]
        min_age = (s.get("MinimumAge") or [None])[0]
        max_age = (s.get("MaximumAge") or [None])[0]
        if not age_in_range(age, min_age, max_age):
            continue
        if not sex_matches(sex, gender):
            continue
        filtered.append(s)

    # If no filtered results but there were raw studies, return top unfiltered to avoid empty UI
    if not filtered and studies:
        return {
            "expr": expr,
            "count": len(studies[:15]),
            "studies": studies[:15],
            "note": "No trials passed local age/sex filters; showing top unfiltered results.",
        }

    return {
        "expr": expr,
        "count": len(filtered),
        "studies": filtered[:15],
    }

# ---------- Routes ----------

@app.route("/api/health", methods=["GET"])  # simple readiness probe
def health():
    return jsonify({"ok": True})


@app.route("/api/extract", methods=["POST"])
def extract():
    payload = request.get_json(force=True)
    transcript = payload.get("transcript", "") if isinstance(payload, dict) else ""
    if not transcript:
        return jsonify({"error": "Missing transcript"}), 400
    data = _gemini_extract(transcript)
    return jsonify({"extracted": data})


@app.route("/api/match", methods=["POST"])
def match():
    payload = request.get_json(force=True)
    transcript = payload.get("transcript", "") if isinstance(payload, dict) else ""
    if not transcript:
        return jsonify({"error": "Missing transcript"}), 400
    extracted = _gemini_extract(transcript)
    results = query_trials(extracted)
    if isinstance(results, dict) and results.get("error"):
        return jsonify({"extracted": extracted, "results": results}), 502
    return jsonify({"extracted": extracted, "results": results})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=True)
