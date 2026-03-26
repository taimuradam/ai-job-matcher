from __future__ import annotations

import math
import re
from collections import Counter
from datetime import UTC, datetime

SKILL_ALIASES: dict[str, set[str]] = {
    "Python": {"python"},
    "FastAPI": {"fastapi"},
    "SQL": {"sql", "postgresql", "mysql", "sqlite", "snowflake"},
    "Pandas": {"pandas"},
    "NumPy": {"numpy"},
    "scikit-learn": {"scikit-learn", "sklearn"},
    "PyTorch": {"pytorch"},
    "TensorFlow": {"tensorflow"},
    "OpenAI API": {"openai api", "openai", "gpt", "gpt-4", "gpt-4o", "llm", "llms"},
    "LangChain": {"langchain"},
    "RAG": {"rag", "retrieval augmented generation", "retrieval-augmented generation"},
    "Docker": {"docker", "containerization"},
    "Kubernetes": {"kubernetes", "k8s"},
    "Git": {"git", "github", "gitlab"},
    "JavaScript": {"javascript", "js"},
    "TypeScript": {"typescript", "ts"},
    "React": {"react", "next.js", "nextjs"},
    "Node.js": {"node.js", "nodejs", "node"},
    "GraphQL": {"graphql"},
    "Redis": {"redis"},
    "REST APIs": {"rest", "restful", "api design", "apis", "api"},
    "Machine Learning": {"machine learning", "ml"},
    "Data Analysis": {"data analysis", "analytics", "analysis"},
    "Data Visualization": {"data visualization", "tableau", "power bi", "matplotlib", "seaborn"},
    "A/B Testing": {"a/b testing", "experimentation"},
    "NLP": {"nlp", "natural language processing"},
    "AWS": {"aws", "amazon web services", "s3", "ec2", "lambda"},
    "Azure": {"azure"},
    "GCP": {"gcp", "google cloud"},
    "CI/CD": {"ci/cd", "continuous integration", "continuous delivery", "github actions"},
    "ETL": {"etl", "data pipeline", "data pipelines", "pipeline orchestration"},
    "Airflow": {"airflow", "apache airflow"},
    "Spark": {"spark", "apache spark"},
    "Terraform": {"terraform", "iac", "infrastructure as code"},
    "Prompt Engineering": {"prompt engineering", "prompt design"},
    "LLM Evaluation": {"llm evaluation", "model evaluation", "prompt evaluation", "evals"},
}

ROLE_LIBRARY: dict[str, dict[str, object]] = {
    "backend engineer": {
        "keywords": {"backend", "api", "microservice", "server", "platform"},
        "skills": {"Python", "FastAPI", "SQL", "Docker", "REST APIs", "AWS", "Git"},
        "adjacent": ["software engineer", "platform engineer", "full stack engineer", "api engineer"],
        "synonyms": ["python developer", "api engineer", "software engineer", "backend developer", "backend platform engineer"],
    },
    "data analyst": {
        "keywords": {"analytics", "dashboard", "reporting", "insights", "sql"},
        "skills": {"Python", "SQL", "Pandas", "NumPy", "Data Analysis", "Data Visualization"},
        "adjacent": ["business intelligence analyst", "data engineer", "product analyst", "analytics engineer"],
        "synonyms": ["analytics engineer", "business analyst", "reporting analyst", "data analytics analyst"],
    },
    "machine learning engineer": {
        "keywords": {"ml", "model", "machine learning", "llm", "nlp"},
        "skills": {"Python", "Machine Learning", "PyTorch", "TensorFlow", "scikit-learn", "NLP", "RAG", "OpenAI API", "Prompt Engineering", "LLM Evaluation"},
        "adjacent": ["data scientist", "ai engineer", "applied scientist", "applied ai engineer"],
        "synonyms": ["ml engineer", "ai engineer", "applied ai engineer", "machine learning developer"],
    },
    "frontend engineer": {
        "keywords": {"frontend", "ui", "ux", "client", "react"},
        "skills": {"JavaScript", "TypeScript", "React", "Node.js"},
        "adjacent": ["full stack engineer", "web engineer", "software engineer", "product engineer"],
        "synonyms": ["ui engineer", "react developer", "web developer", "frontend developer"],
    },
    "full stack engineer": {
        "keywords": {"full stack", "frontend", "backend", "web"},
        "skills": {"Python", "JavaScript", "TypeScript", "React", "SQL", "REST APIs"},
        "adjacent": ["backend engineer", "frontend engineer", "software engineer", "product engineer"],
        "synonyms": ["software engineer", "product engineer", "web engineer", "fullstack engineer", "full stack developer"],
    },
    "software engineer": {
        "keywords": {"software", "engineer", "developer", "applications"},
        "skills": {"Python", "JavaScript", "Git", "REST APIs"},
        "adjacent": ["backend engineer", "frontend engineer", "full stack engineer", "product engineer"],
        "synonyms": ["application engineer", "developer", "software developer", "application developer"],
    },
    "platform engineer": {
        "keywords": {"platform", "infrastructure", "internal tools", "developer tools", "reliability"},
        "skills": {"Python", "Docker", "AWS", "CI/CD", "Kubernetes", "Terraform", "Git"},
        "adjacent": ["backend engineer", "software engineer", "devops engineer"],
        "synonyms": ["backend platform engineer", "infrastructure engineer", "platform developer"],
    },
    "api engineer": {
        "keywords": {"api", "integration", "backend", "services"},
        "skills": {"Python", "REST APIs", "FastAPI", "SQL", "Git"},
        "adjacent": ["backend engineer", "software engineer", "integration engineer"],
        "synonyms": ["integration engineer", "backend engineer", "api developer"],
    },
    "data engineer": {
        "keywords": {"pipeline", "etl", "warehouse", "data platform", "spark"},
        "skills": {"Python", "SQL", "ETL", "Airflow", "Spark", "AWS"},
        "adjacent": ["data analyst", "analytics engineer", "software engineer"],
        "synonyms": ["analytics engineer", "data platform engineer", "etl engineer"],
    },
    "analytics engineer": {
        "keywords": {"analytics engineering", "dbt", "reporting", "warehouse", "metrics"},
        "skills": {"SQL", "Python", "ETL", "Data Analysis", "Data Visualization"},
        "adjacent": ["data analyst", "data engineer", "product analyst"],
        "synonyms": ["analytics developer", "data engineer", "reporting engineer"],
    },
    "product analyst": {
        "keywords": {"product", "experimentation", "funnel", "dashboard", "insights"},
        "skills": {"SQL", "Pandas", "Data Analysis", "A/B Testing", "Data Visualization"},
        "adjacent": ["data analyst", "business intelligence analyst", "analytics engineer"],
        "synonyms": ["growth analyst", "analytics analyst", "business analyst"],
    },
    "business intelligence analyst": {
        "keywords": {"bi", "dashboard", "reporting", "stakeholder", "business intelligence"},
        "skills": {"SQL", "Data Visualization", "Data Analysis", "Pandas"},
        "adjacent": ["data analyst", "product analyst", "analytics engineer"],
        "synonyms": ["bi analyst", "reporting analyst", "insights analyst"],
    },
    "ai engineer": {
        "keywords": {"ai", "llm", "prompt", "agents", "rag"},
        "skills": {"Python", "OpenAI API", "RAG", "Prompt Engineering", "LLM Evaluation", "Docker"},
        "adjacent": ["machine learning engineer", "software engineer", "applied ai engineer"],
        "synonyms": ["applied ai engineer", "llm engineer", "ai developer"],
    },
    "data scientist": {
        "keywords": {"modeling", "statistics", "experimentation", "machine learning", "analysis"},
        "skills": {"Python", "Machine Learning", "Pandas", "scikit-learn", "SQL"},
        "adjacent": ["machine learning engineer", "data analyst", "ai engineer"],
        "synonyms": ["ml scientist", "applied scientist", "research scientist"],
    },
    "web engineer": {
        "keywords": {"web", "frontend", "backend", "javascript", "react"},
        "skills": {"JavaScript", "TypeScript", "React", "Node.js", "REST APIs"},
        "adjacent": ["frontend engineer", "full stack engineer", "software engineer"],
        "synonyms": ["web developer", "frontend engineer", "full stack engineer"],
    },
    "product engineer": {
        "keywords": {"product", "customer", "frontend", "backend", "shipping"},
        "skills": {"JavaScript", "TypeScript", "React", "Python", "SQL"},
        "adjacent": ["software engineer", "full stack engineer", "frontend engineer"],
        "synonyms": ["software engineer", "full stack engineer", "application engineer"],
    },
    "devops engineer": {
        "keywords": {"devops", "infrastructure", "deployment", "kubernetes", "ci/cd"},
        "skills": {"AWS", "Docker", "Kubernetes", "CI/CD", "Terraform", "Git"},
        "adjacent": ["platform engineer", "software engineer", "backend engineer"],
        "synonyms": ["site reliability engineer", "infrastructure engineer", "platform engineer"],
    },
}

INDUSTRY_KEYWORDS: dict[str, set[str]] = {
    "ai": {"llm", "machine learning", "nlp", "rag", "gpt"},
    "fintech": {"finance", "trading", "payments", "banking", "risk"},
    "healthtech": {"clinical", "patient", "medical", "healthcare"},
    "ecommerce": {"checkout", "retail", "cart", "catalog", "marketplace"},
    "developer tools": {"sdk", "developer", "api platform", "tooling", "observability"},
}

STOP_WORDS = {
    "and",
    "for",
    "with",
    "the",
    "that",
    "this",
    "from",
    "into",
    "role",
    "roles",
    "intern",
    "internship",
    "engineer",
    "engineering",
    "developer",
    "analyst",
    "scientist",
    "you",
    "your",
    "build",
    "using",
    "required",
    "requirements",
    "preferred",
    "plus",
    "bonus",
    "team",
    "teams",
    "years",
    "year",
    "experience",
    "work",
}

STATE_ABBREVIATIONS: dict[str, str] = {
    "al": "alabama",
    "ak": "alaska",
    "az": "arizona",
    "ar": "arkansas",
    "ca": "california",
    "co": "colorado",
    "ct": "connecticut",
    "de": "delaware",
    "fl": "florida",
    "ga": "georgia",
    "hi": "hawaii",
    "id": "idaho",
    "il": "illinois",
    "in": "indiana",
    "ia": "iowa",
    "ks": "kansas",
    "ky": "kentucky",
    "la": "louisiana",
    "me": "maine",
    "md": "maryland",
    "ma": "massachusetts",
    "mi": "michigan",
    "mn": "minnesota",
    "ms": "mississippi",
    "mo": "missouri",
    "mt": "montana",
    "ne": "nebraska",
    "nv": "nevada",
    "nh": "new hampshire",
    "nj": "new jersey",
    "nm": "new mexico",
    "ny": "new york",
    "nc": "north carolina",
    "nd": "north dakota",
    "oh": "ohio",
    "ok": "oklahoma",
    "or": "oregon",
    "pa": "pennsylvania",
    "ri": "rhode island",
    "sc": "south carolina",
    "sd": "south dakota",
    "tn": "tennessee",
    "tx": "texas",
    "ut": "utah",
    "vt": "vermont",
    "va": "virginia",
    "wa": "washington",
    "wv": "west virginia",
    "wi": "wisconsin",
    "wy": "wyoming",
    "dc": "district of columbia",
}

REGION_KEYWORDS: dict[str, str] = {
    "united states": "United States",
    "usa": "United States",
    "us": "United States",
    "europe": "Europe",
    "uk": "United Kingdom",
    "canada": "Canada",
    "worldwide": "Worldwide",
    "remote": "Remote",
}

DEGREE_PATTERNS = {
    "Bachelor's": r"\b(bachelor|b\.s\.|bs|b\.a\.|ba)\b",
    "Master's": r"\b(master|m\.s\.|ms|m\.eng)\b",
    "PhD": r"\b(phd|doctorate)\b",
    "Bootcamp": r"\bbootcamp\b",
}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def dedupe_preserve_order(items: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = normalize_text(item)
        if not normalized or normalized in seen:
            continue
        deduped.append(item.strip())
        seen.add(normalized)
    return deduped


def extract_skills(text: str) -> list[str]:
    normalized = normalize_text(text)
    found = {
        canonical
        for canonical, aliases in SKILL_ALIASES.items()
        if any(re.search(rf"(?<!\w){re.escape(alias.lower())}(?!\w)", normalized) for alias in aliases)
    }
    return sorted(found)


def extract_years_of_experience(text: str) -> float | None:
    normalized = normalize_text(text)
    explicit_years = [
        int(match.group(1))
        for match in re.finditer(r"(\d{1,2})\+?\s+(?:years|yrs)\b", normalized)
    ]
    if explicit_years:
        return float(max(explicit_years))

    year_values = [
        int(match.group(0))
        for match in re.finditer(r"\b(20\d{2}|19\d{2})\b", normalized)
    ]
    current_year = datetime.now().year
    plausible_years = [year for year in year_values if 1995 <= year <= current_year]
    if plausible_years:
        return float(max(current_year - min(plausible_years), 0))
    return None


def extract_education(text: str) -> list[str]:
    normalized = normalize_text(text)
    return [label for label, pattern in DEGREE_PATTERNS.items() if re.search(pattern, normalized)]


def extract_resume_signals(text: str, *, limit: int = 5) -> list[str]:
    signals: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if len(stripped) > 150:
            stripped = stripped[:147] + "..."
        if "@" in stripped or stripped.startswith(("http", "www.")):
            continue
        signals.append(stripped)
        if len(signals) == limit:
            break
    return signals


def meaningful_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z\-\+\.#]+", text.lower())
        if token not in STOP_WORDS and len(token) > 2
    }


def cosine_similarity(left_text: str, right_text: str) -> float:
    left_counts = Counter(meaningful_tokens(left_text))
    right_counts = Counter(meaningful_tokens(right_text))
    if not left_counts or not right_counts:
        return 0.0

    shared = set(left_counts) & set(right_counts)
    dot_product = sum(left_counts[token] * right_counts[token] for token in shared)
    left_norm = math.sqrt(sum(value * value for value in left_counts.values()))
    right_norm = math.sqrt(sum(value * value for value in right_counts.values()))
    if not left_norm or not right_norm:
        return 0.0
    return dot_product / (left_norm * right_norm)


def extract_matching_lines(text: str, keywords: set[str], *, limit: int = 4) -> list[str]:
    matches: list[str] = []
    for line in text.splitlines():
        normalized = normalize_text(line)
        if not normalized:
            continue
        if any(keyword in normalized for keyword in keywords):
            matches.append(line.strip())
        if len(matches) >= limit:
            break
    return matches


def expand_role_aliases(role: str) -> list[str]:
    normalized = normalize_text(role)
    aliases = [role]
    role_profile = ROLE_LIBRARY.get(normalized, {})
    if isinstance(role_profile, dict):
        aliases.extend(role_profile.get("synonyms", []))
        aliases.extend(role_profile.get("adjacent", []))

    replacements = (
        ("software developer", "software engineer"),
        ("backend developer", "backend engineer"),
        ("frontend developer", "frontend engineer"),
        ("fullstack", "full stack"),
        ("ml engineer", "machine learning engineer"),
        ("applied ai", "ai"),
        ("backend platform", "platform"),
    )
    for source, target in replacements:
        if source in normalized:
            aliases.append(normalized.replace(source, target))
        if target in normalized:
            aliases.append(normalized.replace(target, source))
    if "engineer" in normalized:
        aliases.append(normalized.replace("engineer", "developer"))
    if "developer" in normalized:
        aliases.append(normalized.replace("developer", "engineer"))
    return dedupe_preserve_order(aliases)


def extract_location_mentions(text: str, *, limit: int = 5) -> list[str]:
    normalized = normalize_text(text)
    locations: list[str] = []

    for region_key, region_label in REGION_KEYWORDS.items():
        if re.search(rf"(?<![a-z]){re.escape(region_key)}(?![a-z])", normalized):
            locations.append(region_label)

    city_state_matches = re.findall(r"\b([A-Z][a-z]+(?:[\s-][A-Z][a-z]+)*,\s*[A-Z]{2})\b", text)
    locations.extend(city_state_matches)

    for abbreviation, state_name in STATE_ABBREVIATIONS.items():
        if re.search(rf"(?<![a-z]){re.escape(abbreviation)}(?![a-z])", normalized):
            locations.append(state_name.title())
        if state_name in normalized:
            locations.append(state_name.title())

    for line in text.splitlines():
        stripped = line.strip(" -")
        if not stripped:
            continue
        lowered = normalize_text(stripped)
        if any(marker in lowered for marker in ("based in", "located in", "location", "remote", "hybrid")) and len(stripped) <= 80:
            locations.append(stripped)

    return dedupe_preserve_order(locations)[:limit]


def parse_iso_age_days(value: str | None) -> int | None:
    if not value:
        return None
    cleaned = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    return max((datetime.now(UTC) - parsed.astimezone(UTC)).days, 0)
