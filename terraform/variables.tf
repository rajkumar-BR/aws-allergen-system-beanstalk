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

variable "python_version_regex" {
  description = "Regex used to pick the Elastic Beanstalk Python solution stack."
  type        = string
  default     = "^64bit Amazon Linux 2023.*Python 3\\.12$"
}
