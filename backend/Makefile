$project :=
$version := grow-ext-cloud-images

deploy:
	gcloud app deploy \
		-q \
		--project=$(project) \
		--version=$(version) \
		--no-promote \
		app.yaml
