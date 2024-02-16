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
		OpenaiApiKey=${OPENAI_API_KEY}