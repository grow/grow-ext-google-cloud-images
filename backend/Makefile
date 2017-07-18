$project :=

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
		--promote \
		app.yaml
