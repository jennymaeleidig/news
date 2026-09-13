
# Direct feeds

The sources you subscribe to in your reader — no feed is generated for
them here. Generated from [`sources.toml`](../sources.toml); edit the
registry, not this file:

```
python -m feeds gen --direct-table docs/direct-feeds.md
```

| Feed | Site | Why it's here | Feed URL |
|------|------|---------------|----------|
| radarai.top | [radarai.top](https://radarai.top) | Aggregator by design; links go off-site. | `https://radarai.top/en/feed.xml` |
| AI Hero Skills | [aihero.dev](https://www.aihero.dev) |  | `https://www.aihero.dev/skills/rss.xml` |
| Democracy Now! | [democracynow.org](https://www.democracynow.org) |  | `https://www.democracynow.org/democracynow.rss` |
| Drop Site News | [dropsitenews.com](https://www.dropsitenews.com) | Full text. | `https://www.dropsitenews.com/feed` |
| The 51st | [51st.news](https://51st.news) |  | `https://51st.news/rss/` |
| 404 Media | [404media.co](https://www.404media.co) | Full text. | `https://www.404media.co/rss/` |
| User Mag | [usermag.co](https://www.usermag.co) |  | `https://www.usermag.co/feed` |
| Aftermath | [aftermath.site](https://aftermath.site) | Full text. | `https://aftermath.site/rss/` |
| Wired | [wired.com](https://www.wired.com) | Summary only (~140 chars). | `https://www.wired.com/feed/rss` |
| Morning Brew | [morningbrew.com](https://www.morningbrew.com) |  | `https://www.morningbrew.com/feed.xml` |
| Jason Schreier (YouTube) | [youtube.com](https://www.youtube.com/@jasonschreier) |  | `https://www.youtube.com/feeds/videos.xml?channel_id=UCQoOmu6mKZkXTnwZcpD8Ciw` |
| ProPublica | [propublica.org](https://www.propublica.org) | Full articles. | `https://www.propublica.org/feeds/propublica/main` |
| Defector | [defector.com](https://defector.com) |  | `https://defector.com/feed` |
| Ken Klippenstein | [kenklippenstein.com](https://www.kenklippenstein.com) | Full text. | `https://www.kenklippenstein.com/feed` |
| NPR News | [npr.org](https://www.npr.org) |  | `https://feeds.npr.org/1001/rss.xml` |
| PBS NewsHour | [pbs.org](https://www.pbs.org/newshour) | Direct — the old Safari user-agent override was deleted; PBS serves the standard browser string fine. | `https://www.pbs.org/newshour/feeds/rss/headlines` |
| Majority Report (YouTube) | [youtube.com](https://www.youtube.com/@TheMajorityReport) |  | `https://www.youtube.com/feeds/videos.xml?channel_id=UC-3jIAlnQmbbVMV6gR7K8aQ` |
| HasanAbi (YouTube) | [youtube.com](https://www.youtube.com/@hasanabi) |  | `https://www.youtube.com/feeds/videos.xml?channel_id=UCtoaZpBnrd0lhycxYJ4MNOQ` |
| True Anon | [patreon.com](https://www.patreon.com/truelit) | Unlisted first-party Patreon podcast feed; mixes [PREVIEW] stubs with free episodes. | `https://www.patreon.com/public-rss/2963533?show=875184` |
| Buddha in the Mud | [buddhainthemud.com](https://buddhainthemud.com) | Full text. | `https://buddhainthemud.com/feed/` |
| Lazy Sundays | [lazysundays.net](https://www.lazysundays.net) | Summary only (~125 chars). | `https://www.lazysundays.net/feed` |
