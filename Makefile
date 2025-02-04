lint:
	make black-lint
	make flake8-lint
	make mypy-lint

black-format:
	poetry run black .

black-lint:
	poetry run black . --check

flake8-lint:
	poetry run flake8

mypy-lint:
	poetry run mypy --no-namespace-packages .

build:
	sam build

sam-package-dev:
	sam package \
		--region us-west-2 \
		--image-repository ${DEV_AWS_ACCOUNT_ID}.dkr.ecr.us-west-2.amazonaws.com/transcriber-lambda-dev \
		--s3-bucket transcriber-lambda-builds-${STAGE_NAME} \
		--s3-prefix api_builds \
		--output-template-file packaged.yaml

sam-deploy-dev:
	make build
	make sam-package-dev

	sam deploy \
		--region us-west-2 \
		--image-repository ${DEV_AWS_ACCOUNT_ID}.dkr.ecr.us-west-2.amazonaws.com/transcriber \
		--no-fail-on-empty-changeset \
		--template-file packaged.yaml \
		--stack-name TRANSCRIBER-LAMBDA-DEV \
		--capabilities CAPABILITY_IAM --parameter-overrides StageName=${STAGE_NAME} \
		AccountId=${DEV_AWS_ACCOUNT_ID} \
		OpenaiApiKey=${OPENAI_API_KEY}