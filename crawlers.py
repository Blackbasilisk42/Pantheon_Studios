import os
import requests
from bs4 import BeautifulSoup


def run_intelligent_crawler():
  print("\n--- Pantheon Studios: Autonomous Learning Crawler ---")
  target_url = input(
      "Enter target URL for intelligence and lore sourcing: "
  ).strip()
  if not target_url:
    print("No URL provided. Aborting scan.")
    return

  try:
    headers = {
        "User-Agent": (
            "PantheonStudiosAI-Learner/2.0 (Autonomous Knowledge Agent)"
        )
    }
    response = requests.get(target_url, headers=headers, timeout=12)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    page_title = soup.title.string.strip() if soup.title else "Untitled Source"

    # Extract all paragraph data to analyze depth and narrative structure
    paragraphs = [p.get_text().strip() for p in soup.find_all("p") if p.get_text()]
    full_body_text = "\n\n".join(paragraphs)

    # Simple heuristic-based adaptive metric: evaluating content volume and density
    word_count = len(full_body_text.split())
    density_score = (
        "High Value / Rich Context" if word_count > 200 else "Sparse / Brief Data"
    )

    print(f"[*] Target Acquired: {page_title}")
    print(
        f"[*] Adaptive Metrics - Word Count: {word_count} | Rating:"
        f" {density_score}"
    )

    # Generate a smart local log file optimizing for future retrieval and learning loops
    safe_name = "".join(
        c for c in page_title if c.isalnum() or c in (" ", "_", "-")
    ).strip()
    filename = f"intelligence_log_{safe_name.replace(' ', '_')}.md"

    with open(filename, "w", encoding="utf-8") as f:
      f.write(f"# Intelligence Report: {page_title}\n\n")
      f.write(f"**Source URL:** {target_url}\n")
      f.write(f"**Analysis Rating:** {density_score} ({word_count} words)\n\n")
      f.write("## Extracted Knowledge Core\n")
      f.write(
          full_body_text
          if full_body_text
          else "No substantial text extracted."
      )
      f.write(
          "\n\n--- \n*Note: Log structured for autonomous learning and lore"
          " optimization.*"
      )

    print(
        f"[+] Intelligence successfully synthesized and saved to {filename}"
    )

  except Exception as e:
    print(f"[!] Autonomous Crawler Exception Encountered: {e}")


if __name__ == "__main__":
  run_intelligent_crawler()