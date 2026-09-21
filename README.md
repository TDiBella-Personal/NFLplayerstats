# Our Guys

Phone app for tracking favorite NFL players. Season line, last game, bio, past teams, and a short human-interest story per player. Shared favorites between two phones.

Three pieces:

1. **This repo on GitHub Pages** - the app (`index.html`) plus nightly data (`data/*.json`) that a GitHub Action rebuilds every morning at 5am ET from free nflverse feeds.
2. **One Cloudflare Worker** (`worker/worker.js`) - holds the shared favorites list and the saved stories, and keeps the Anthropic API key off the page.
3. **An Anthropic API key** with a few dollars of credit. Stories cost a few cents each, once per player, ever.

## Setup (about 30 minutes, all in a browser)

### 1. GitHub (10 min)
1. Use the public repo `TDiBella-Personal/NFLplayerstats`.
2. Upload everything in this folder. The `.github/workflows/pull.yml` file must land at that exact path. Easiest on a Mac: drag the whole folder contents into the repo's "upload files" page.
3. Repo Settings > Pages > Source: **Deploy from a branch**, branch `main`, folder `/ (root)`. Save. Your app URL is `https://tdibella-personal.github.io/NFLplayerstats/`.
4. Repo Settings > Actions > General > Workflow permissions: **Read and write permissions**. Save.
5. Actions tab > "Nightly stats pull" > **Run workflow**. Takes about 2 minutes. If it turns green, the nightly refresh works.

At this point the app runs with favorites saved per phone and no stories. Test it before continuing.

### 2. Cloudflare Worker (15 min)
1. Sign up at dash.cloudflare.com (free plan is fine).
2. **Storage & Databases > KV** > Create namespace, name it `our-guys`.
3. **Compute (Workers) > Create** > "Start with Hello World" > name it `our-guys` > Deploy.
4. Open the worker > **Edit code** > replace everything with the contents of `worker/worker.js` > Deploy.
5. Worker > **Settings > Bindings > Add** > KV namespace. Variable name `OG`, pick the `our-guys` namespace.
6. Worker > **Settings > Variables and Secrets > Add**:
   - `PAGES_ORIGIN` (text) = `https://YOUR-USERNAME.github.io`
   - `ANTHROPIC_API_KEY` (secret) = your key from console.anthropic.com
   - `MODEL` (text) = `claude-sonnet-4-6` (optional)
   - `DAILY_STORY_CAP` (text) = `40` (optional, protects your credit)
7. Copy the worker URL from the overview page, something like `https://our-guys.YOUR-NAME.workers.dev`.

### 3. Connect them (2 min)
1. In the repo, edit `index.html`. Near the top of the script: `var WORKER = "";` - paste the worker URL between the quotes. Commit.
2. Wait a minute for Pages to redeploy, then open the app. Favorites header should say "Shared" and cards get a "Get his story" button.

### 4. Phones (1 min each)
Open the app URL in Safari > Share > **Add to Home Screen**. Do it on both phones. Same link, same favorites.

## How it works
- `scripts/pull.py` reads nflverse weekly stats, PFR advanced defense, the player table, and 2000-present rosters. Writes `data/players.json`, `data/stats.json`, `data/meta.json`. Run it locally with `python3 scripts/pull.py`.
- Stats are per completed game. They update overnight, not live.
- Advanced defensive numbers (coverage, pressures) come from a separate feed that lags a day or so. The drawer shows which week it is through.
- Stories: the worker asks Claude to web-search the player and return 3-4 one-sentence facts, or nothing if it finds nothing solid. Saved forever in KV after the first tap.
- The worker only answers requests from your GitHub Pages origin and caps story generation per day. It is not bulletproof, it is a couple-bucks-a-season app.

## Things you might change later
- `LAYOUT` in `index.html`: which stats show per position.
- `DEFAULT` favorites: there are none. Star players from their cards.
- Side-by-side compare, career totals: not built yet.
