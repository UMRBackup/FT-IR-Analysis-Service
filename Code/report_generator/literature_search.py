import os
import serpapi

try:
    SERP_API_KEY: str = os.environ["SERP_API_KEY"]
except KeyError:
    SERP_API_KEY = ""
    print("Warning: Missing SERP_API_KEY")

def search_literature_and_cite(keyword, max_results=3):
    if not SERP_API_KEY:
        print("Notice: SERP_API_KEY is not configured, skipping literature search.")
        return []

    search_params = {
        "engine": "google_scholar",
        "q": keyword,
        "hl": "en",
    }

    client = serpapi.Client(api_key=SERP_API_KEY)

    results = client.search(search_params)
    organic_results = results.get("organic_results", [])

    citations = []
    # 选取最多 max_results 个结果
    for result in organic_results[:max_results]:
        result_id = result.get("result_id")
        if not result_id:
            continue

        # 获取引用格式
        cite_params = {
            "engine": "google_scholar_cite",
            "q": result_id,
        }
        cite_search = client.search(cite_params)
        cite_results = cite_search.get("cite_results", {})

        # 提取 APA 格式
        apa_snippet = None
        for citation in cite_results.get("citations", []):
            if citation.get("title") == "APA":
                apa_snippet = citation.get("snippet")
                break

        if apa_snippet:
            citations.append({
                "title": result.get("title"),
                "link": result.get("link"),
                "apa_citation": apa_snippet
            })

    return citations

def main():
    keyword = input("请输入要检索的关键词：")
    citations = search_literature_and_cite(keyword)
    for idx, citation in enumerate(citations, 1):
        print(f"{idx}. {citation['title']}")
        print(f"   Link: {citation['link']}")
        print(f"   APA Citation: {citation['apa_citation']}\n")

if __name__ == "__main__":
    main()