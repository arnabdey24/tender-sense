"""Generate the development and demo dataset.

Writes three files under ``data/``:

* ``seed/tenders.json``      — 40 notices spanning the shapes the pipeline must
  handle: strong fits, near misses, clear rejects, missing attributes, expired
  and imminent deadlines, and both e-GP Bangladesh and World Bank styles.
* ``seed/sample_company.json`` — a Dhaka systems integrator to match against.
* ``eval/labels.csv``        — relevance 0/1/2 per tender for that company,
  which is what ``eval_matching.py`` scores semantic matching against a keyword
  baseline with.

Deterministic: the same seed always produces the same dataset, so a change in
matching quality is attributable to the model or thresholds rather than to the
data moving underneath it.

Usage: ``uv run python -m scripts.gen_synthetic``
"""

from __future__ import annotations

import csv
import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

RANDOM_SEED = 20260909
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REFERENCE_NOW = datetime(2026, 9, 9, 6, 0, tzinfo=UTC)

# Relevance for the sample company: 2 strong fit, 1 plausible, 0 irrelevant.
STRONG, PLAUSIBLE, IRRELEVANT = 2, 1, 0

BD_BUYERS = [
    "Local Government Engineering Department",
    "Bangladesh Computer Council",
    "Directorate General of Health Services",
    "Bangladesh Bank",
    "Ministry of Education, Secondary and Higher Education Division",
    "Rural Electrification Board",
    "Bangladesh Water Development Board",
    "National Board of Revenue",
]

WB_COUNTRIES = ["Bangladesh", "Nepal", "Sri Lanka", "Kenya", "Viet Nam"]

# (title, summary, category, label)
ICT_STRONG = [
    (
        "Design, development and implementation of a management information system",
        "Consulting services to design, build and roll out a national MIS covering "
        "data collection, dashboards and reporting for programme monitoring.",
        "consulting",
        STRONG,
    ),
    (
        "Capacity building in digital governance for public sector institutions",
        "Technical assistance to strengthen digital service delivery, including "
        "systems architecture review, training and change management.",
        "consulting",
        STRONG,
    ),
    (
        "Supply, installation and commissioning of enterprise network infrastructure",
        "Procurement and deployment of switching, routing and wireless equipment "
        "across 24 district offices, with three years of support.",
        "goods",
        STRONG,
    ),
    (
        "Development of an e-government service portal and mobile application",
        "Build a citizen-facing portal with single sign-on, payment integration "
        "and an accompanying mobile application.",
        "consulting",
        STRONG,
    ),
    (
        "IT consulting services for digital transformation roadmap",
        "Advisory engagement to assess current systems and produce a costed "
        "digital transformation roadmap.",
        "consulting",
        STRONG,
    ),
    (
        "Implementation of a hospital information management system",
        "Configure and deploy a hospital information system across eight "
        "district hospitals, including data migration and training.",
        "consulting",
        STRONG,
    ),
    (
        "Establishment of a data centre and disaster recovery site",
        "Design and build a tier-3 data centre with a geographically separate "
        "disaster recovery facility.",
        "works",
        STRONG,
    ),
    (
        "Software development services for a revenue management platform",
        "Custom development of a tax revenue management platform with "
        "integration to existing banking interfaces.",
        "consulting",
        STRONG,
    ),
    (
        "Cyber security assessment and ISO 27001 readiness support",
        "Security assessment, gap analysis and support towards ISO 27001 "
        "certification for a public financial institution.",
        "consulting",
        STRONG,
    ),
    (
        "Supply and installation of servers, storage and virtualisation software",
        "Hardware and licensing for a consolidated virtualisation platform, "
        "including migration of existing workloads.",
        "goods",
        STRONG,
    ),
]

ICT_PLAUSIBLE = [
    (
        "Procurement of desktop computers, printers and peripherals",
        "Bulk supply of end-user computing equipment to field offices.",
        "goods",
        PLAUSIBLE,
    ),
    (
        "Digitisation of paper land records",
        "Scanning, indexing and quality assurance of archived land records, "
        "with delivery into an existing repository.",
        "services",
        PLAUSIBLE,
    ),
    (
        "Supply of biometric attendance devices",
        "Provision and installation of fingerprint attendance terminals with "
        "a central reporting interface.",
        "goods",
        PLAUSIBLE,
    ),
    (
        "Third-party monitoring of a rural connectivity programme",
        "Independent verification of broadband rollout milestones, including "
        "field surveys and reporting.",
        "consulting",
        PLAUSIBLE,
    ),
    (
        "Training services on data analysis for government statisticians",
        "Curriculum design and delivery of statistical analysis training.",
        "services",
        PLAUSIBLE,
    ),
    (
        "Call centre operations and support services",
        "Staffing and operation of a citizen helpline, including a ticketing "
        "system and monthly performance reporting.",
        "services",
        PLAUSIBLE,
    ),
    (
        "Supply of GPS tracking units for a vehicle fleet",
        "Hardware, SIM provisioning and a web interface for fleet tracking.",
        "goods",
        PLAUSIBLE,
    ),
    (
        "Feasibility study for a shared government cloud",
        "Assessment of demand, costing and procurement options for a shared "
        "cloud hosting facility.",
        "consulting",
        PLAUSIBLE,
    ),
]

UNRELATED = [
    (
        "Construction of a two-lane regional highway, package RHD-14",
        "Earthworks, pavement, drainage and bridge works over 42 kilometres.",
        "works",
        IRRELEVANT,
    ),
    (
        "Supply of pharmaceutical products and medical consumables",
        "Annual framework for the supply of essential medicines.",
        "goods",
        IRRELEVANT,
    ),
    (
        "Rehabilitation of irrigation canals and regulators",
        "Desilting, lining and structural repair of canal systems.",
        "works",
        IRRELEVANT,
    ),
    (
        "Procurement of fertiliser for the boro season",
        "Supply and delivery of urea to regional warehouses.",
        "goods",
        IRRELEVANT,
    ),
    (
        "Catering and housekeeping services for a residential training centre",
        "Daily catering, cleaning and laundry services.",
        "services",
        IRRELEVANT,
    ),
    (
        "Construction of a multipurpose cyclone shelter",
        "Reinforced concrete shelter with water and sanitation facilities.",
        "works",
        IRRELEVANT,
    ),
    (
        "Supply and installation of solar irrigation pumps",
        "Photovoltaic pumping systems for smallholder irrigation.",
        "goods",
        IRRELEVANT,
    ),
    (
        "Demolition of derelict municipal structures",
        "Controlled demolition and debris removal.",
        "works",
        IRRELEVANT,
    ),
    (
        "Printing of textbooks for primary education",
        "Printing, binding and distribution of textbooks.",
        "goods",
        IRRELEVANT,
    ),
    (
        "Supply of school furniture",
        "Manufacture and delivery of desks and benches.",
        "goods",
        IRRELEVANT,
    ),
    (
        "Dredging of a river channel to restore navigability",
        "Capital dredging with disposal of dredged material.",
        "works",
        IRRELEVANT,
    ),
    (
        "Security guarding services for regional offices",
        "Provision of trained security personnel on a 24-hour roster.",
        "services",
        IRRELEVANT,
    ),
    (
        "Supply of laboratory reagents and glassware",
        "Consumables for public health laboratories.",
        "goods",
        IRRELEVANT,
    ),
    (
        "Construction of staff quarters, package LGED-77",
        "Six-storey residential building including external works.",
        "works",
        IRRELEVANT,
    ),
    (
        "Vehicle maintenance and repair services",
        "Scheduled servicing and repair of a government vehicle fleet.",
        "services",
        IRRELEVANT,
    ),
    (
        "Supply of uniforms and protective clothing",
        "Manufacture and delivery of field staff uniforms.",
        "goods",
        IRRELEVANT,
    ),
    (
        "Afforestation and nursery development programme",
        "Raising seedlings and plantation across coastal belts.",
        "services",
        IRRELEVANT,
    ),
    (
        "Installation of street lighting on municipal roads",
        "Supply and erection of LED street lighting with poles.",
        "works",
        IRRELEVANT,
    ),
    (
        "Procurement of ambulances",
        "Supply of fully equipped ambulances to district hospitals.",
        "goods",
        IRRELEVANT,
    ),
    (
        "Consultancy for a water supply master plan",
        "Hydraulic modelling and investment planning for municipal water supply.",
        "consulting",
        IRRELEVANT,
    ),
    (
        "Supply of office stationery",
        "Annual supply of paper, files and general stationery.",
        "goods",
        IRRELEVANT,
    ),
    (
        "Rehabilitation of a rural health complex building",
        "Civil repair works including roofing and sanitation.",
        "works",
        IRRELEVANT,
    ),
]

SAMPLE_COMPANY: dict[str, Any] = {
    "name": "Meghna Systems Limited",
    "country": "BD",
    "website": "https://meghnasystems.example",
    "description": (
        "A Dhaka-based systems integrator delivering management information "
        "systems, e-government platforms and enterprise network infrastructure "
        "for public sector and development partner programmes."
    ),
    "sectors": ["information_technology", "public_administration", "health", "education"],
    "geographies": ["BD", "NP", "LK"],
    "annual_turnover": {"amount": 620000000, "currency": "BDT", "year": 2025},
    "services": [
        {
            "name": "Management information systems",
            "description": (
                "Design, development and rollout of MIS platforms with dashboards, "
                "reporting and data quality tooling."
            ),
        },
        {
            "name": "E-government platforms",
            "description": (
                "Citizen-facing portals and mobile applications with single sign-on "
                "and payment gateway integration."
            ),
        },
        {
            "name": "Enterprise network and data centre infrastructure",
            "description": (
                "Supply, installation and support of switching, routing, servers, "
                "storage and virtualisation platforms."
            ),
        },
        {
            "name": "Digital governance advisory",
            "description": (
                "Assessments, roadmaps, capacity building and change management for "
                "public sector digital transformation."
            ),
        },
        {
            "name": "Information security services",
            "description": (
                "Security assessments, ISO 27001 readiness and security operations support."
            ),
        },
    ],
    "certifications": [
        {"code": "ISO_9001", "name": "ISO 9001:2015", "issuer": "BSI", "valid_until": "2028-03-31"},
        {
            "code": "ISO_27001",
            "name": "ISO/IEC 27001:2022",
            "issuer": "BSI",
            "valid_until": "2027-11-30",
        },
        {
            "code": "CMMI_DEV_3",
            "name": "CMMI-DEV Level 3",
            "issuer": "ISACA",
            "valid_until": "2027-06-30",
        },
    ],
    "past_projects": [
        {
            "title": "National health management information system",
            "client": "Directorate General of Health Services",
            "country": "BD",
            "sector": "health",
            "year_completed": 2024,
            "value_amount": 180000000,
            "currency": "BDT",
            "role": "prime",
            "description": (
                "Built and rolled out a national health MIS covering 64 districts, "
                "including data migration, dashboards and training."
            ),
        },
        {
            "title": "Education sector e-service portal",
            "client": "Ministry of Education",
            "country": "BD",
            "sector": "education",
            "year_completed": 2023,
            "value_amount": 95000000,
            "currency": "BDT",
            "role": "prime",
            "description": (
                "Citizen portal for scholarship applications with single sign-on and "
                "online payment."
            ),
        },
        {
            "title": "District network modernisation",
            "client": "Rural Electrification Board",
            "country": "BD",
            "sector": "information_technology",
            "year_completed": 2025,
            "value_amount": 240000000,
            "currency": "BDT",
            "role": "prime",
            "description": (
                "Supplied and installed network infrastructure across 30 sites with a "
                "three-year support agreement."
            ),
        },
        {
            "title": "Revenue systems assessment",
            "client": "National Board of Revenue",
            "country": "BD",
            "sector": "public_administration",
            "year_completed": 2022,
            "value_amount": 42000000,
            "currency": "BDT",
            "role": "prime",
            "description": "Assessment and roadmap for revenue system modernisation.",
        },
        {
            "title": "Local government data centre",
            "client": "Local Government Division",
            "country": "NP",
            "sector": "information_technology",
            "year_completed": 2024,
            "value_amount": 1100000,
            "currency": "USD",
            "role": "jv",
            "description": "Data centre design and build delivered in joint venture.",
        },
    ],
    "keyword_exclusions": ["demolition", "dredging", "afforestation"],
    "contract_value_range": {
        "min": {"amount": 50000, "currency": "USD"},
        "max": {"amount": 8000000, "currency": "USD"},
    },
    "procurement_methods": ["OTM", "ICB", "NCB", "QCBS", "RFP"],
}


def _deadline(rng: random.Random, bucket: str) -> datetime | None:
    """Deadlines are spread deliberately so urgency handling has real cases."""
    if bucket == "expired":
        return REFERENCE_NOW - timedelta(days=rng.randint(2, 20))
    if bucket == "critical":
        return REFERENCE_NOW + timedelta(days=rng.randint(0, 3), hours=rng.randint(0, 12))
    if bucket == "soon":
        return REFERENCE_NOW + timedelta(days=rng.randint(4, 7))
    if bucket == "none":
        return None
    return REFERENCE_NOW + timedelta(days=rng.randint(8, 60))


def build_dataset() -> tuple[list[dict[str, Any]], list[tuple[str, int]]]:
    rng = random.Random(RANDOM_SEED)
    entries = [*ICT_STRONG, *ICT_PLAUSIBLE, *UNRELATED]

    # A deterministic spread of deadline shapes across the set.
    buckets = ["normal"] * 26 + ["soon"] * 5 + ["critical"] * 3 + ["expired"] * 4 + ["none"] * 2
    rng.shuffle(buckets)

    tenders: list[dict[str, Any]] = []
    labels: list[tuple[str, int]] = []

    for index, ((title, summary, category, label), bucket) in enumerate(
        zip(entries, buckets, strict=True)
    ):
        world_bank = index % 3 == 2
        source_code = "wb" if world_bank else "egp_bd"
        external_id = f"OP{4600000 + index:07d}" if world_bank else f"{1330000 + index * 7}"
        country = rng.choice(WB_COUNTRIES) if world_bank else "Bangladesh"
        deadline = _deadline(rng, bucket)

        # Roughly one in eight notices withholds its value, which is what makes
        # "needs verification" a real state rather than a theoretical one.
        has_value = index % 8 != 3
        currency = "USD" if world_bank else "BDT"
        value = None
        if has_value:
            value = (
                round(rng.uniform(120_000, 4_500_000), 2)
                if world_bank
                else round(rng.uniform(8_000_000, 420_000_000), 2)
            )

        tenders.append(
            {
                "source_code": source_code,
                "external_id": external_id,
                "canonical_url": (
                    f"https://projects.worldbank.org/en/projects-operations/"
                    f"procurement-detail/{external_id}"
                    if world_bank
                    else f"https://www.eprocure.gov.bd/resources/common/"
                    f"ViewTender.jsp?id={external_id}"
                ),
                "title": title,
                "summary": summary,
                "description": (
                    f"{summary} Bidders must demonstrate relevant experience and "
                    "financial capacity. Full details are given in the bidding document."
                ),
                "procuring_entity": (
                    f"{country} — Ministry of Planning" if world_bank else rng.choice(BD_BUYERS)
                ),
                "country": {
                    "Bangladesh": "BD",
                    "Nepal": "NP",
                    "Sri Lanka": "LK",
                    "Kenya": "KE",
                    "Viet Nam": "VN",
                }[country],
                "procurement_method": rng.choice(
                    ["ICB", "QCBS", "RFP"] if world_bank else ["OTM", "LTM", "RFQ"]
                ),
                "procurement_category": category,
                "published_at": (REFERENCE_NOW - timedelta(days=rng.randint(0, 21))).isoformat(),
                "deadline_at": deadline.isoformat() if deadline else None,
                "currency": currency if has_value else None,
                "estimated_value": value,
                "status": "closed" if bucket == "expired" else "open",
                "language": "en",
                "portal_metadata": {
                    "notice_type": "Request for Expression of Interest"
                    if world_bank
                    else "Invitation for Tender",
                    "synthetic": True,
                },
            }
        )
        labels.append((external_id, label))

    return tenders, labels


def main() -> None:
    tenders, labels = build_dataset()

    seed_dir = DATA_DIR / "seed"
    eval_dir = DATA_DIR / "eval"
    seed_dir.mkdir(parents=True, exist_ok=True)
    eval_dir.mkdir(parents=True, exist_ok=True)

    (seed_dir / "tenders.json").write_text(json.dumps(tenders, indent=2) + "\n")
    (seed_dir / "sample_company.json").write_text(json.dumps(SAMPLE_COMPANY, indent=2) + "\n")

    with (eval_dir / "labels.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["external_id", "relevance"])
        writer.writerows(labels)

    counts = {score: sum(1 for _, label in labels if label == score) for score in (2, 1, 0)}
    print(f"wrote {len(tenders)} tenders to {seed_dir / 'tenders.json'}")
    print(f"labels: {counts[2]} strong, {counts[1]} plausible, {counts[0]} irrelevant")


if __name__ == "__main__":
    main()
