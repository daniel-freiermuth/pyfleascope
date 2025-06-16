upload_to_pypi:
	python3 -m build
	python3 -m twine upload --repository pypi dist/*
