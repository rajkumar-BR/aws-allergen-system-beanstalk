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

# ---- Knowledge Base outputs (only when create_knowledge_base = true) ----
output "knowledge_base_id" {
  value       = var.create_knowledge_base ? aws_bedrockagent_knowledge_base.peal[0].id : ""
  description = "Bedrock Knowledge Base ID for RAG retrieval (set KNOWLEDGE_BASE_ID env var)"
}

output "knowledge_base_arn" {
  value       = var.create_knowledge_base ? aws_bedrockagent_knowledge_base.peal[0].arn : ""
  description = "Bedrock Knowledge Base ARN"
}

output "kb_docs_bucket" {
  value       = var.create_knowledge_base ? aws_s3_bucket.kb_docs[0].bucket : ""
  description = "S3 bucket containing PEAL reference documents"
}

output "data_source_id" {
  value       = var.create_knowledge_base ? aws_bedrockagent_data_source.peal[0].id : ""
  description = "Knowledge Base Data Source ID (for manual ingestion trigger)"
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
    5. If Knowledge Base is enabled (create_knowledge_base = true):
       - Get KB ID: terraform output knowledge_base_id
       - Set env var: export KNOWLEDGE_BASE_ID=$(terraform output -raw knowledge_base_id)
       - Trigger ingestion: aws bedrock-agent start-ingestion-job \
           --knowledge-base-id $(terraform output -raw knowledge_base_id) \
           --data-source-id $(terraform output -raw data_source_id) \
           --region ${var.aws_region}
  EOT
}
