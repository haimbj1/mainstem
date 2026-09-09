# Publish runbook (manual, owner-only)

This repo is never pushed or made into a GitHub repo by an agent. Before the owner does that by
hand:

1. Run the CI checks locally (see CONTRIBUTING.md) — must be clean.
2. Run a full gitleaks history scan: `gitleaks detect --source . --log-opts="--all"`.
3. Run a manual grep audit over the tree for a blocklist the owner keeps locally (never in this
   repo) — real name, company names, org slug, Jira host, ticket prefixes, home paths, provider
   names. The list itself must never be committed here; it lives in the owner's local config dir.
4. **Check commit author/committer identity, not just file content**: `git log --format='%an
   <%ae>%n%cn <%ce>' | sort -u`. Neither gitleaks' default rules nor this repo's own CI hygiene
   grep (Milestone 6) inspect this — both scan tracked file content/diffs, not commit metadata —
   so a real name/email embedded here (the local machine's global `git config`, inherited by
   every commit unless the repo overrides it) survives every other check silently. Found during
   this plan's own execution (Milestone 11): every commit up to that point carried the real
   owner's identity. If any commit here isn't already a placeholder, rewrite history once, now,
   as the very last step before publish — never mid-build, since a rewrite changes every commit
   hash and would invalidate any in-progress bookkeeping that references specific SHAs. Example,
   replacing every author/committer identity with a fixed placeholder (`pip install git-filter-repo`
   first; run this on a throwaway clone, not the working copy you're still using):

   (the email placeholder below is deliberately not written as a literal `name@host` string, so
   it does not itself trip this repo's own CI hygiene grep for embedded email addresses):

   ```bash
   git filter-repo --force \
     --name-callback 'return b"MainStem"' \
     --email-callback 'return ("noreply" + chr(64) + "example.invalid").encode()'
   ```

   Verify with the same command from step 4 (`git log --format='%an <%ae>%n%cn <%ce>' | sort -u`)
   that only the placeholder identity remains, then push the rewritten history to the new,
   still-private GitHub repo.
5. Eyeball the final tree by hand.
6. Create the GitHub repo PRIVATE first. Only flip it public after steps 1-5 are clean.
