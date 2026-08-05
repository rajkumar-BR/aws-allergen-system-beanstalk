variable "aws_region" {
  description = "AWS region to deploy into. Must be a region where Bedrock and Textract are both available."
  type        = string
  default     = "ap-southeast-2" # Sydney - closest Bedrock-enabled region to NZ at time of writing
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
  default     = "anthropic.claude-3-haiku-20240307-v1:0"
}

variable "python_version_regex" {
  description = "Regex used to pick the Elastic Beanstalk Python solution stack."
  type        = string
  default     = "^64bit Amazon Linux 2023.*Python 3\\.12$"
}
