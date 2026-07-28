# Build the report PDF from the Markdown source with md2pdf (WeasyPrint).
# On macOS/Apple-Silicon WeasyPrint needs the Homebrew pango/gdk-pixbuf libs,
# hence the DYLD_FALLBACK_LIBRARY_PATH. On Linux this var is simply ignored.
#
# Requires md2pdf: python3 -m pip install "md2pdf[cli]"
# Override MD2PDF if yours lives elsewhere, e.g. make MD2PDF=md2pdf

DYLD := DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib
# Invoke via the venv python: a shebang can't point into a path with spaces.
MD2PDF := .venv/bin/python .venv/bin/md2pdf

default: report.pdf

report.pdf: README.md
	$(DYLD) $(MD2PDF) -i $< -o $@

.PHONY: clean
clean:
	rm -f report.pdf
