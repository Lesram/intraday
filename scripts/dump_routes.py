from backend.api.factory import create_app

app = create_app()
rows = []
for r in app.routes:
    path = getattr(r, "path", "")
    name = getattr(r, "name", "")
    methods = sorted(list(getattr(r, "methods", []) or []))
    rows.append((path, ",".join(methods), name))

print("PATH\tMETHODS\tNAME")
for path, methods, name in sorted(rows):
    print(f"{path}\t{methods}\t{name}")
