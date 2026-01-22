from atproto import Client


def main():
    client = Client()
    client.login("judgedirac.bsky.social", "Soccer03!")

    data = client.get_profile(actor="wotcmatt.bsky.social")
    did = data.did

    all_posts = get_all_posts(client, did)
    for p in all_posts:
        find_wotc_staff(p, client)


def get_all_posts(client, did, responses=[], cursor=None):
    posts = client.get_author_feed(did, cursor=cursor)
    responses.append(posts)

    if posts.cursor is not None:
        get_all_posts(client, did, responses, cursor=posts.cursor)

    return responses


def find_wotc_staff(posts, client):
    out = []
    for post in posts.feed:
        if "#WotCstaff".lower() in post.post.record.text.lower():
            if post.reply is not None:
                try:
                    pass
                except Exception:
                    pass
            out.append(post)
    return out


if __name__ == "__main__":
    main()
