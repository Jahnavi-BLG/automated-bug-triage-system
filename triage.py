"""Triage engine: preprocessing, classification (NLP/ML), duplicate detection, assignee recommendation."""
import csv, os, re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline

TRAIN_CSV = os.path.join(os.path.dirname(__file__), "data", "training.csv")
SEV_ORDER = ["Low", "Medium", "High", "Critical"]
SLA_HOURS = {"Critical": 4, "High": 24, "Medium": 72, "Low": 168}
DUP_THRESHOLD = 0.60

# Rule hints: if a strong keyword appears, severity is never lower than this (hybrid ML + rules).
SEV_RULES = [
    ("Critical", r"\b(crash(es|ed)?|data loss|lost data|corrupt\w*|outage|sql injection|breach|completely down|fatal)\b"),
    ("High", r"\b(500 error|exception|timeout|times out|unable to|cannot|can't|not working)\b"),
]


def preprocess(text: str) -> str:
    """Step 2 of the pipeline: clean and normalise text."""
    t = text.lower()
    t = re.sub(r"https?://\S+", " url ", t)          # links
    t = re.sub(r"0x[0-9a-f]+|\b\d{4,}\b", " num ", t)  # memory addresses / long numbers
    t = re.sub(r"[^a-z0-9\s]", " ", t)               # punctuation
    return re.sub(r"\s+", " ", t).strip()


def priority_from(severity: str, component: str) -> str:
    """P1 (urgent) .. P4 (low). Payments/auth issues are bumped one level."""
    base = {"Critical": 1, "High": 2, "Medium": 3, "Low": 4}[severity]
    if component in ("payments", "auth") and base > 1:
        base -= 1
    return f"P{base}"


class Classifier:
    TARGETS = ("type", "severity", "component")

    def __init__(self):
        self.models, self.accuracy, self.n_train = {}, {}, 0
        self.train()

    @staticmethod
    def _load():
        with open(TRAIN_CSV, encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def train(self, extra_rows=None):
        rows = self._load() + (extra_rows or [])
        X = [preprocess(r["text"]) for r in rows]
        self.n_train = len(rows)
        for target in self.TARGETS:
            y = [r[target] for r in rows]
            mk = lambda: make_pipeline(TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True),
                                       LogisticRegression(max_iter=2000, C=12))
            Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=1)
            self.accuracy[target] = round(float(mk().fit(Xtr, ytr).score(Xte, yte)), 3)  # hold-out accuracy
            self.models[target] = mk().fit(X, y)                                       # final model on all data

    def predict(self, text: str) -> dict:
        x, out, conf = [preprocess(text)], {}, {}
        for target, model in self.models.items():
            p = model.predict_proba(x)[0]
            i = int(np.argmax(p))
            out[target], conf[target] = str(model.classes_[i]), float(p[i])
        for level, pattern in SEV_RULES:  # rule boost
            if re.search(pattern, text.lower()) and SEV_ORDER.index(level) > SEV_ORDER.index(out["severity"]):
                out["severity"], conf["severity"] = level, max(conf["severity"], 0.9)
            if re.search(pattern, text.lower()):
                break
        out["priority"] = priority_from(out["severity"], out["component"])
        out["confidence"] = {k: round(v, 2) for k, v in conf.items()}
        return out


_CORPUS = None
def _stem(text: str) -> str:
    """Very light stemmer so 'crashes/crashed/crashing' all match 'crash'."""
    return " ".join(re.sub(r"(ing|ed|es|s)$", "", w) if len(w) > 4 else w for w in preprocess(text).split())


def _corpus():
    global _CORPUS
    if _CORPUS is None:
        with open(TRAIN_CSV, encoding="utf-8") as f:
            _CORPUS = [_stem(r["text"]) for r in csv.DictReader(f)]
    return _CORPUS


def find_duplicates(text: str, candidates: list, threshold: float = DUP_THRESHOLD, limit: int = 3) -> list:
    """Step 4: TF-IDF cosine similarity against open issues (IDF learned from the training corpus)."""
    if not candidates:
        return []
    vec = TfidfVectorizer(stop_words="english", sublinear_tf=True).fit(_corpus())
    m = vec.transform([_stem(c["text"]) for c in candidates] + [_stem(text)])
    sims = cosine_similarity(m[-1], m[:-1])[0]
    hits = [{"id": c["id"], "score": round(float(s), 2)} for c, s in zip(candidates, sims) if s >= threshold]
    return sorted(hits, key=lambda h: -h["score"])[:limit]


def rank_developers(component: str, developers: list, cap: int = 8) -> list:
    """Step 5: score = 60% skill match + 40% free capacity.  developers: [{id,name,skills,load}]"""
    ranked = []
    for d in developers:
        skills = [s.strip() for s in d["skills"].split(",") if s.strip()]
        skill = 1.0 if component in skills else 0.0
        free = max(0.0, 1 - d["load"] / cap)
        ranked.append({"id": d["id"], "name": d["name"], "skills": skills, "load": d["load"],
                       "score": round(0.6 * skill + 0.4 * free, 2),
                       "reason": ("skill match" if skill else "no skill match") + f", {d['load']} open issue(s)"})
    return sorted(ranked, key=lambda r: (-r["score"], r["load"]))
