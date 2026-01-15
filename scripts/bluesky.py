from atproto import Client, models


def main():
    client = Client()
    client.login("judgedirac.bsky.social", 'Soccer03!')


    data = client.get_profile(actor='wotcmatt.bsky.social')
    did = data.did
    display_name = data.display_name
    print(did)
    print(display_name)


    all_posts = get_all_posts(client, did)
    print(len(all_posts))
    for p in all_posts:
        find_wotc_staff(p, client)

def get_all_posts(client,did, responses=[], cursor=None):
    posts = client.get_author_feed(did, cursor=cursor)
    responses.append(posts)

    print(posts.cursor)
    if posts.cursor is not None:

        get_all_posts(client, did, responses, cursor=posts.cursor)
    #print(len(responses))

    

    return responses


def find_wotc_staff(posts, client):
    out = []
    for post in posts.feed:
        if "#WotCstaff".lower() in post.post.record.text.lower():
            print(post.post.embed)
           
            print(type(post))
            print(type(post.post))
            if post.reply is not None:
                try:
                    print(type(post.reply.root))
                   
                    print(post.reply.root.record.text)
                except Exception as e:
                    print(post.reply.root.not_found)
                    print("reply deleted")
            out.append(post)
            print(post.post.record.text)
        print("\n\n")
    return out

if __name__ == "__main__":
    main()