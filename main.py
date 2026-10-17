def create_post(title, content):
    filename = f"{title.replace(' ', '_')}.md"
    with open(filename, "w") as file:
        file.write(f"# {title}\n\n{content}")
    print(f"Post '{title}' created successfully.")


if __name__ == "__main__":
    post_title = "My First Post"
    post_content = "This is the content of my first post."
    create_post(post_title, post_content)