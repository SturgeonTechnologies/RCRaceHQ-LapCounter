# Building and releasing the app image

The lap counter app (`app/`) ships as **one container image** for
`linux/arm64` (Pi 4). The same image runs every service; compose picks the
command (`web` = gunicorn, `lapd` = `python -m lapcounter.lapd`).

Installing it on a Pi is done by
[RCRaceHQ-LapCounter-Deploy](https://github.com/SturgeonTechnologies/RCRaceHQ-LapCounter-Deploy)
(`deploy_lapcounter_app.yml`), which pulls a pinned tag from ECR.

```
PR ──► CI: pytest + arm64 build (no push)
main ─► CI: pytest + arm64 build ─► ECR :sha-<7 chars>
tag vX.Y.Z ─► CI: pytest + arm64 build ─► ECR :vX.Y.Z
                                              │
         Deploy repo inventory: lapcounter_app_image_tag ─► Pi pulls it
```

Registry: `587449585882.dkr.ecr.us-west-2.amazonaws.com/rcracehq/lapcounter`.
Tags are **immutable**: a tag always means the same image, so a Pi that has it
never needs to pull it again, and CI skips tags that already exist.

## Components in the image

| Service | Command | Port | What |
|---|---|---|---|
| `web` | `gunicorn --worker-class gthread … 'lapcounter.web:create_app()'` (image default) | 8080 | First-run setup, admin sign-in, public live view (SSE), `/healthz` |
| `lapd` | `python -m lapcounter.lapd` | — | Subscribes to OpenStint's ZeroMQ feed, writes passings + decoder stats to SQLite |

- Base `python:3.12-slim-bookworm`, two stages (wheel build, then install).
- Runs as `lapcounter` (uid 10001). `/var/lib/lapcounter` is the only
  writable path that matters (SQLite in WAL mode, shared by both services).
- Healthcheck: `GET http://127.0.0.1:8080/healthz` every 30 s (disabled for
  `lapd`, which has no port).
- Env: `LAPCOUNTER_DB`, `OPENSTINT_ZMQ`, `LAPCOUNTER_DECODER_STALE_S`; see
  [app/README.md](../app/README.md#environment).

## Build locally

```bash
cd app
docker compose up --build                  # native arch, web on :8080
docker buildx build --platform linux/arm64 -t lapcounter:dev .   # Pi arch (QEMU on x86)
```

Without Docker: see [app/README.md](../app/README.md#run).

## Release

- **Every merge to `main`** that touches `app/` pushes `:sha-<first 7 of the
  commit>`. Use these for testing on a Pi.
- **A release**: tag the commit and push the tag.

  ```bash
  git tag -a v0.1.0 -m "lapcounter v0.1.0" && git push origin v0.1.0
  ```

  CI pushes `:v0.1.0`. Bump `version` in `app/pyproject.toml` in the same PR
  so the package version matches.

Then in the deploy repo set `lapcounter_app_image_tag` (inventory) and run
`deploy_lapcounter_app.yml`. The run summary in GitHub Actions shows the exact
tag that was pushed.

List what's in ECR:

```bash
aws ecr describe-images --region us-west-2 --repository-name rcracehq/lapcounter \
  --query 'reverse(sort_by(imageDetails,&imagePushedAt))[:10].[imageTags,imagePushedAt]' --output table
```

## One-time AWS setup (us-west-2)

CI pushes only once the repo variable `AWS_ECR_PUSH_ROLE_ARN` is set; until
then the `image` job still builds (so Dockerfile breakage shows up) but skips
the push. Run these from the repo root with an admin profile.

**1. ECR repository** (immutable tags, scan on push, lifecycle: keep 30 newest
`sha-*`, never expire `v*`, drop untagged after 7 days):

```bash
aws ecr create-repository --region us-west-2 --repository-name rcracehq/lapcounter \
  --image-tag-mutability IMMUTABLE --image-scanning-configuration scanOnPush=true
aws ecr put-lifecycle-policy --region us-west-2 --repository-name rcracehq/lapcounter \
  --lifecycle-policy-text file://docs/iam/ecr-lifecycle.json
```

**2. CI push role** `LapCounterImagePush`, assumable only by GitHub Actions
runs from this repo's `main` branch or `v*` tags (not PRs, not forks). It uses
the account's existing GitHub OIDC provider (the one RCRaceHQ's deploy
workflow uses):

```bash
aws iam create-role --role-name LapCounterImagePush \
  --assume-role-policy-document file://docs/iam/lapcounter-image-push-trust.json \
  --description "GitHub Actions (RCRaceHQ-LapCounter main/v* tags) pushes the app image to ECR"
aws iam put-role-policy --role-name LapCounterImagePush \
  --policy-name LapCounterEcrPush \
  --policy-document file://docs/iam/lapcounter-image-push.json
```

Check it:

```bash
aws iam list-open-id-connect-providers     # must list token.actions.githubusercontent.com
aws iam get-role --role-name LapCounterImagePush --query 'Role.[Arn,AssumeRolePolicyDocument]'
aws iam list-role-policies --role-name LapCounterImagePush   # LapCounterEcrPush
```

**3. Repo variable** (a variable, not a secret; the ARN isn't sensitive):

```bash
gh variable set AWS_ECR_PUSH_ROLE_ARN -R SturgeonTechnologies/RCRaceHQ-LapCounter \
  --body arn:aws:iam::587449585882:role/LapCounterImagePush
```

**4. Let the Pis pull**: the `RaceDecoderEcrPull` inline policy on
`RaceDecoderSSMNode`, in the deploy repo's
[deploy_lapcounter_app.md](https://github.com/SturgeonTechnologies/RCRaceHQ-LapCounter-Deploy/blob/main/docs/deploy_lapcounter_app.md#one-time-aws-setup-us-west-2).

Push the first image: **Actions → app → Run workflow** on `main` (or
`gh workflow run app.yml -R SturgeonTechnologies/RCRaceHQ-LapCounter --ref main`).
It pushes `:sha-<7>` of the current `main`.

| File | What |
|---|---|
| [`iam/lapcounter-image-push-trust.json`](iam/lapcounter-image-push-trust.json) | OIDC trust: `aud=sts.amazonaws.com`, `sub` = this repo's `main` or `v*` tags |
| [`iam/lapcounter-image-push.json`](iam/lapcounter-image-push.json) | `GetAuthorizationToken` + push/describe on `rcracehq/lapcounter` only |
| [`iam/ecr-lifecycle.json`](iam/ecr-lifecycle.json) | ECR lifecycle rules above |
