output "app_url" {
  description = "Open this in a browser to use the UI once the environment status is 'Ready'."
  value       = "http://${aws_elastic_beanstalk_environment.env.cname}"
}

output "eb_environment_name" {
  value = aws_elastic_beanstalk_environment.env.name
}

output "eb_application_name" {
  value = aws_elastic_beanstalk_application.app.name
}

output "menu_uploads_bucket" {
  value = aws_s3_bucket.menu_uploads.bucket
}

output "eb_app_versions_bucket" {
  value = aws_s3_bucket.eb_app_versions.bucket
}

output "dynamodb_table_name" {
  value = aws_dynamodb_table.menu_items.name
}

output "cognito_user_pool_id" {
  value = aws_cognito_user_pool.staff_pool.id
}

output "next_steps" {
  value = <<-EOT
    1. Wait for `eb_environment_name` health to show "Green"/"Ready":
       aws elasticbeanstalk describe-environments --environment-names ${aws_elastic_beanstalk_environment.env.name} --query "Environments[0].Status"
    2. Open app_url in a browser.
    3. Click "Load Sample Menu" to run the full OCR-skip -> allergen
       analyze -> compliance verify -> translate pipeline on 8 sample dishes.
    4. Make sure Bedrock model access is granted for
       ${var.bedrock_model_id} in ${var.aws_region} (Bedrock console ->
       Model access) - without it, allergen extraction/translation will
       silently fall back to the offline keyword-scan / Amazon Translate
       stubs instead of the LLM.
  EOT
}
