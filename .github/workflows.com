name: Nightly stats pull
on:
  schedule:
    - cron: "0 9 * * *"   # 5am ET (9:00 UTC), daily
  workflow_dispatch:
permissions:
  contents: write
jobs:
  pull:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python scripts/pull.py
      - name: Commit data
        run: |
          git config user.name "our-guys-bot"
          git config user.email "bot@users.noreply.github.com"
          git add data
          git diff --cached --quiet || git commit -m "data: $(date -u +%F)"
          git push
