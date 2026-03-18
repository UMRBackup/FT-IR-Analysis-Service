import os
import requests
from typing import Optional, Dict, Any

try:
    CAS_API: str = os.environ["CAS_API_KEY"]
except KeyError:
    CAS_API =  ""
    print("Warning: Missing CAS_API_KEY environment variable")

def cas_search(query: str) -> Optional[Dict[str, Any]]:
    if not CAS_API:
        print("Warning: CAS_API_KEY not configured, skipping search")
        return None

    url = "https://commonchemistry.cas.org/api/search"
    headers = {
        "accept": "application/json",
        "X-API-KEY": CAS_API
    }
    params = {
        "q": query
    }

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"CAS Request Failed: {e}")
        return None

def cas_detail(cas_number: str) -> Optional[Dict[str, Any]]:
    if not CAS_API:
        print("Warning: CAS_API_KEY not configured, skipping query")
        return None

    url = "https://commonchemistry.cas.org/api/detail"
    headers = {
        "accept": "application/json",
        "X-API-KEY": CAS_API
    }
    params = {
        "cas_rn": cas_number
    }

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"CAS Request Failed: {e}")
        return None

def get_compound_info(query: str) -> Optional[Dict[str, Any]]:
    search_data = cas_search(query)
    if not search_data or not search_data.get("results"):
        print(f"No search results found for compound '{query}'")
        return None

    # 获取搜索结果中第一个化合物的 rn
    first_result = search_data["results"][0]
    rn = first_result.get("rn")
    name = first_result.get("name", query)

    if not rn:
        print(f"Could not find 'rn' field in search results")
        return None

    # 根据 rn 获取化合物详细信息
    detail_data = cas_detail(rn)
    if not detail_data:
        print(f"Failed to fetch detailed info for compound {rn}")
        return None

    return {
        "name": name,
        "rn": rn,
        "molecularFormula": detail_data.get("molecularFormula"),
        "molecularMass": detail_data.get("molecularMass"),
        "image": detail_data.get("image"),
        "images": detail_data.get("images")
    }

def main():
    query = input("请输入要搜索的化合物名称 / Please enter the compound name to search: ").strip()
    if not query:
        print("No input provided, exiting")
        return

    compound_info = get_compound_info(query)
    if compound_info:
        print(f"Compound Name: {compound_info['name']}")
        print(f"CAS RN: {compound_info['rn']}")
        print(f"Molecular Formula: {compound_info['molecularFormula']}")
        print(f"Molecular Mass: {compound_info['molecularMass']}")

if __name__ == "__main__":
    main()