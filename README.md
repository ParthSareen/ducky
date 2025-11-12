# rubber ducky

Generates bash commands to use quickly within your terminal


## tl;dr
- `uv tool install rubber-ducky` (or `uv pip install rubber-ducky` inside a project)
- Install [ollama](https://ollama.com)
- `ollama pull qwen3-coder:480b-cloud` (first time and then you can just have application in background)
- `ducky` for multi-line inputs and `ducky` for quick bash commands 

## Dependencies

You will need Ollama installed on your machine. The default model used for this project is `qwen3-coder:480b-cloud`.

Run `ollama pull qwen3-coder:480b-cloud` to have it enabled for your machine


Ollama is also great because it'll spin up a server which can run in the background and can even do automatic model switching as long as you have it installed.

## Usage

Install through [PyPI](https://pypi.org/project/rubber-ducky/) with uv:

`uv tool install rubber-ducky`

If you prefer a project-local installation, use `uv pip install rubber-ducky` from within your repository.

### Simple run
`ducky`

or 

`ducky <question>`

or 

`ducky --directory <path>`


### All options
`ducky --directory <directory> --model <model>`

Where:
- `--directory` or `-d`: The directory to be processed
- `--model` or `-m`: The model to be used (default is "qwen3-coder:480b-cloud")

## Development with uv

This repository ships a `pyproject.toml` and `uv.lock`, so the recommended workflow is:

```
uv sync
uv run ducky --help
```

`uv sync` will create an isolated environment with the project dependencies, while `uv run` lets you execute CLI commands without activating the environment manually.


## Example output
![Screenshot of ducky](image.png)
