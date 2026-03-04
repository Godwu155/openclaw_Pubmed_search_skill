#!/usr/bin/env python3
"""PubMed search skill script.

This script is designed to be executed by the OpenClaw agent in a tightly
controlled environment. It only performs HTTP queries against the NCBI
E-utilities API and prints JSON results to stdout.

Security precautions are included to ensure that the script cannot be used
for directory traversal or writing outside the designated skill folder.
"""

import argparse
import json
import os
import sys
import requests
import xml.etree.ElementTree as ET

# Constants for the allowed workspace directory.
SKILL_DIR = os.path.abspath(os.path.dirname(__file__))


def enforce_path(msg=""):
    """Ensure the current working directory is inside the approved skill path.

    This defensive check helps prevent accidental or malicious changes of
    working directory before the script performs any file operations.
    """
    cwd = os.path.abspath(os.getcwd())
    if not cwd.startswith(SKILL_DIR):
        raise RuntimeError(
            f"Script executed outside allowed directory: {cwd}. {msg}"
        )


import xml.etree.ElementTree as ET

def search_pubmed(query, limit):
    """Perform PubMed search & return structured data including full abstract and DOI."""
    # Step 1: esearch to get PMIDs
    esearch_url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    )
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": limit,
        "retmode": "json",
    }
    res = requests.get(esearch_url, params=params, timeout=10)
    res.raise_for_status()
    data = res.json()

    pmids = data.get("esearchresult", {}).get("idlist", [])
    if not pmids:
        return []

    # Step 2: efetch to retrieve full records (xml)
    efetch_url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    )
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
    }
    res = requests.get(efetch_url, params=params, timeout=10)
    res.raise_for_status()
    xml_text = res.text

    # parse the XML response
    root = ET.fromstring(xml_text)
    articles = []
    for pubmed_article in root.findall(".//PubmedArticle"):
        pmid = pubmed_article.findtext(".//PMID")
        title = pubmed_article.findtext(".//ArticleTitle")

        # authors list
        authors = []
        for a in pubmed_article.findall(".//AuthorList/Author"):
            collective = a.findtext("CollectiveName")
            if collective:
                authors.append(collective)
                continue
            last = a.findtext("LastName")
            fore = a.findtext("ForeName")
            if last and fore:
                authors.append(f"{fore} {last}")
            elif last:
                authors.append(last)

        # publication date (year month day if available)
        pubdate = None
        pd = pubmed_article.find(".//Journal/JournalIssue/PubDate")
        if pd is not None:
            year = pd.findtext("Year")
            month = pd.findtext("Month")
            day = pd.findtext("Day")
            parts = [p for p in (year, month, day) if p]
            pubdate = " ".join(parts) if parts else None

            # assemble abstract text
            abstract_parts = []
            for at in pubmed_article.findall(".//Abstract/AbstractText"):
                # 使用 itertext() 抓取包含嵌套标签在内的所有完整文本
                text_content = "".join(at.itertext()).strip()
                if not text_content:
                    continue

                # 尝试获取 PubMed 官方的段落标签（例如 "BACKGROUND", "METHODS"）
                label = at.attrib.get("Label")
                if label:
                    abstract_parts.append(f"{label}: {text_content}")
                else:
                    abstract_parts.append(text_content)

            # 用换行符将各段落拼接，确保 Agent 读到的排版清晰且符合逻辑
            abstract_text = "\n".join(abstract_parts)

        # retrieve DOI if present
        doi = None
        for aid in pubmed_article.findall(".//ArticleIdList/ArticleId"):
            if aid.attrib.get("IdType") == "doi":
                doi = aid.text
                break
        doi_url = f"https://doi.org/{doi}" if doi else None

        articles.append({
            "pmid": pmid,
            "title": title,
            "authors": authors,
            "pubdate": pubdate,
            "abstract": abstract_text,
            "doi_url": doi_url,
        })
    return articles


def main():
    enforce_path("Aborting to maintain directory confinement.")

    parser = argparse.ArgumentParser(description="Search PubMed for articles")
    parser.add_argument("--query", required=True, help="Search terms")
    parser.add_argument(
        "--limit", type=int, default=5, help="Maximum number of results"
    )
    args = parser.parse_args()

    try:
        results = search_pubmed(args.query, args.limit)
        output = {"status": "success", "data": results}
    except Exception as exc:
        output = {"status": "error", "message": str(exc)}

    # Print as JSON to stdout; never evaluate this output as code.
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
