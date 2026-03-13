"""CLI entry point."""
import typer

app = typer.Typer(help="{{ name }} - {{ description }}")


@app.command()
def hello(name: str = typer.Argument("World", help="Name to greet")):
    """Say hello."""
    typer.echo(f"Hello, {name}!")


if __name__ == "__main__":
    app()
