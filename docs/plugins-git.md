# Git Plugin Reference

The git tools live in `src/udan/plugins_tools_examples/plugins_git.py`, declared under
the domain `git` (22 tools). They shell out to the `git` CLI and cover commits, diffs,
status, untracked files, stashes and the org-diff render family.

Because the directory argument defaults to the current directory, the examples below
assume you run them from a git repository root.

## Inserters

`insert_diff(commit_arg="HEAD", directory="", staged=False, words=False, file="")`
Inserts one `GitDiffFile` per changed file. Default render is `org-diff`.

```bash
udan "insert_diff"
```

`commits(directory="", limit=10)` - alias `log`
Inserts `{repo_path, commit_hash}` dicts. The first positional argument is a
directory, not a ref; use `limit` for history depth. Default render is `commit-log`.

```bash
udan "commits"
udan "commits --limit=3, :list"
```

`insert_status(directory="", modified=None)`
Inserts `{status, path}` dicts; status codes are git's short form (`??`, `M`, `A`,
`D`). Default render is `status-path`.

```bash
udan "insert_status, :list"
udan "insert_status --modified=True"
```

`git_repos(directory=".")`
Inserts the paths of every directory under `directory` that contains a `.git`
subdirectory.

```bash
udan "git_repos ."
```

`insert_stash_list(directory="")`
Inserts the lines of `git stash list`. Default render is `org-stash-diff`.

```bash
udan "insert_stash_list"
```

## Extenders

- `extend_commit_files(item)` - changed file paths of a commit. Accepts a commit
  dict, a `GitCommit`, a hash string, or a `hash:path` string that limits the paths
  to ones under `path`.
- `extend_diff_hunks(item)` - one `DiffHunk` per hunk of a `GitDiffFile`.
- `extend_stash_show(item)` - `GitDiffFile` per changed file of a stash entry.
- `untracked(item)` - untracked file paths of a repository (str/Path, or an item
  carrying `repo_path`).

```bash
udan "commits --limit=1, extend_commit_files"
udan "git_repos ., untracked"
```

## Attributes

| Attribute | Returns |
|---|---|
| `git_diff_file_size` | additions + deletions of a `GitDiffFile` |
| `commit_message` | subject line of a commit |
| `push_status` | `UNPUSHED` when the commit is on no remote branch, else `""` |
| `untracked_count` | number of untracked files in a repository |
| `untracked_size` | total size in bytes of the untracked files |
| `hunk_content` | the diff text of a `DiffHunk` |

```bash
udan "commits --limit=2, commit_message"
```

## Renders

| Alias | Renders |
|---|---|
| `commit-log` | one log line per commit: `<date> <short hash> :: <message>`, ` ...` when the body is non-empty, ` / UNPUSHED` when unpushed |
| `org-diff` | `** <file> ( +A -D )` heading with the diff in a `#+begin_src diff` block |
| `org-diff-hunk` | one `*** <file> (hunk N)` heading per hunk, with a `:PROPERTIES:` drawer |
| `org-commit-diff` | commits and their changed files as nested org headings |
| `org-stash-diff` | stash names as `* ` headings, their `GitDiffFile` children as `** ` headings |
| `status-path` | the file path only |
| `status-full` | `<status> <path>` |

```bash
udan "insert_status, status-full"
```

## See also

- `? git` - the tool listing filtered to tools whose name or description matches
  `git` (this domain's tools, plus any others that match)
- [writing_tools.md](writing_tools.md) - how tools of these kinds are written
