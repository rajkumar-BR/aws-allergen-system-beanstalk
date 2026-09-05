variable "aws_region" {
  description = "AWS region to deploy into. Must be a region where Bedrock and Textract are both available."
  type        = string
  default     = "us-east-1" # Broadest Bedrock model availability
}

variable "aws_profile" {
  description = "AWS CLI named profile to use for credentials. Set to \"default\" if you configured credentials without a named profile."
  type        = string
  default     = "personal"
}

variable "project_name" {
  description = "Short name used as a prefix for all resources."
  type        = string
  default     = "allergen-demo"
}

variable "environment" {
  description = "Environment name tag (dev/test/prod)."
  type        = string
  default     = "dev"
}

variable "instance_type" {
  description = "EC2 instance type for the Beanstalk environment."
  type        = string
  default     = "t3.small"
}

variable "min_instances" {
  type    = number
  default = 1
}

variable "max_instances" {
  type    = number
  default = 2
}

variable "bedrock_model_id" {
  description = "Bedrock model ID used for allergen extraction + translation."
  type        = string
  default     = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
}

variable "create_knowledge_base" {
  description = "OPT-IN: provision the Bedrock Knowledge Base for the compliance RAG layer (see bedrock_kb.tf). Off by default so the demo stack is unchanged."
  type        = bool
  default     = false
}

variable "knowledge_base_id" {
  description = "Bedrock Knowledge Base id the app retrieves from for compliance verification. Empty = app runs rules-only (with local keyword retrieval over bundled docs/)."
  type        = string
  default     = ""
}

variable "bedrock_embedding_model_arn" {
  description = "Bedrock embedding model ARN used to index the knowledge base. Default is Amazon Titan Text Embeddings v2 in the default region (ap-southeast-2); change if you deploy elsewhere."
  type        = string
  default     = "arn:aws:bedrock:ap-southeast-2::foundation-model/amazon.titan-embed-text-v2:0"
}

variable "python_version_regex" {
  description = "Regex used to pick the Elastic Beanstalk Python solution stack."
  type        = string
  default     = "^64bit Amazon Linux 2023.*Python 3\\.12$"
}
