$project :=

install:
	pip install -r requirements.txt -t lib

run:
	dev_appserver.py app.yaml

deploy-dispatch:
	gcloud app deploy \
		-q \
		--project=$(project) \
		dispatch.yaml

deploy:
	gcloud app deploy \
		-q \
		--project=$(project) \
		--version=auto \
		--promote \
		app.yaml
