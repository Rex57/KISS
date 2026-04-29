# Project Map Reference

Use this when the user asks what a project does, how it works, or how to run it.

## Read Order

1. File tree with `rg --files` when available.
2. README and docs.
3. Package or build files: `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod`, `requirements.txt`, `Makefile`.
4. Env examples: `.env.example`, `.env.sample`, `example.env`.
5. Main source entry points.
6. Test files only when they clarify behavior.

## Ignore By Default

Do not inspect heavy generated folders unless the user asks:

```text
.git
node_modules
dist
build
.next
coverage
.cache
```

## Output

Start with a graph or setup table.

Then include:

```text
What this project does
1. ...

How it works
1. ...

How to run it
1. ...

Next step
1. ...
```

## Secret Handling

Read env example files. Do not expose secret values from real `.env` files. If a real `.env` file is relevant, say which keys exist without showing values.
