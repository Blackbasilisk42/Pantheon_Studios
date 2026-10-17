import os


def create_post():
  print("\n--- Pantheon Studios Post Creator ---")
  post_title = input("Enter the post title: ").strip()
  if not post_title:
    print("Title cannot be empty.")
    return

  post_content = input("Enter the post content/body: ").strip()

  filename = f"{post_title.replace(' ', '_')}.md"

  # Ensures it saves right in the open workspace folder
  with open(filename, "w", encoding="utf-8") as file:
    file.write(f"# {post_title}\n\n{post_content}\n")

  print(f"\nSuccess! Created file: {filename}")


if __name__ == "__main__":
  create_post()