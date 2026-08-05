# ---------------------------------------------------------------------------
# EC2 instance role - what the Flask app running on each Beanstalk instance
# is allowed to call (Bedrock, Textract, S3, DynamoDB, Translate fallback).
# This is the direct replacement for the Lambda execution role in the
# original Amplify/Lambda architecture.
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "ec2_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    effect  = "Allow"
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "eb_ec2_role" {
  name               = "${local.name_prefix}-eb-ec2-role"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume_role.json
  tags               = local.common_tags
}

# AWS-managed policy required for standard Beanstalk health/metrics reporting.
resource "aws_iam_role_policy_attachment" "eb_web_tier" {
  role       = aws_iam_role.eb_ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/AWSElasticBeanstalkWebTier"
}

data "aws_iam_policy_document" "app_permissions" {
  # S3 - raw menu upload storage
  statement {
    sid    = "MenuUploadsBucket"
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:GetObject",
      "s3:ListBucket",
    ]
    resources = [
      aws_s3_bucket.menu_uploads.arn,
      "${aws_s3_bucket.menu_uploads.arn}/*",
    ]
  }

  # DynamoDB - menu/allergen/translation metadata
  statement {
    sid    = "MenuItemsTable"
    effect = "Allow"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:GetItem",
      "dynamodb:DeleteItem",
      "dynamodb:Query",
      "dynamodb:Scan",
      "dynamodb:UpdateItem",
    ]
    resources = [
      aws_dynamodb_table.menu_items.arn,
      "${aws_dynamodb_table.menu_items.arn}/index/*",
    ]
  }

  # Textract - OCR does not support resource-level ARN scoping
  statement {
    sid    = "TextractOcr"
    effect = "Allow"
    actions = [
      "textract:DetectDocumentText",
      "textract:AnalyzeDocument",
    ]
    resources = ["*"]
  }

  # Bedrock - allergen extraction + translation. No knowledge-base /
  # RAG permissions are granted, per project scope (no bedrock:Retrieve*,
  # no bedrock-agent-runtime actions).
  statement {
    sid    = "BedrockInvoke"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = ["*"]
  }

  # Amazon Translate - only used as a fallback if a Bedrock call itself fails
  statement {
    sid    = "TranslateFallback"
    effect = "Allow"
    actions = [
      "translate:TranslateText",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "app_permissions" {
  name   = "${local.name_prefix}-app-permissions"
  policy = data.aws_iam_policy_document.app_permissions.json
}

resource "aws_iam_role_policy_attachment" "app_permissions_attach" {
  role       = aws_iam_role.eb_ec2_role.name
  policy_arn = aws_iam_policy.app_permissions.arn
}

resource "aws_iam_instance_profile" "eb_ec2_profile" {
  name = "${local.name_prefix}-eb-ec2-profile"
  role = aws_iam_role.eb_ec2_role.name
}

# ---------------------------------------------------------------------------
# Elastic Beanstalk service role - what the Beanstalk control plane itself
# (not your app) is allowed to do, e.g. manage the ASG/ELB behind the
# environment and publish enhanced health data.
# ---------------------------------------------------------------------------
data "aws_iam_policy_document" "eb_service_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    effect  = "Allow"
    principals {
      type        = "Service"
      identifiers = ["elasticbeanstalk.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "sts:ExternalId"
      values   = ["elasticbeanstalk"]
    }
  }
}

resource "aws_iam_role" "eb_service_role" {
  name               = "${local.name_prefix}-eb-service-role"
  assume_role_policy = data.aws_iam_policy_document.eb_service_assume_role.json
  tags               = local.common_tags
}

resource "aws_iam_role_policy_attachment" "eb_service_enhanced_health" {
  role       = aws_iam_role.eb_service_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSElasticBeanstalkEnhancedHealth"
}

resource "aws_iam_role_policy_attachment" "eb_service_managed_updates" {
  role       = aws_iam_role.eb_service_role.name
  policy_arn = "arn:aws:iam::aws:policy/AWSElasticBeanstalkManagedUpdatesCustomerRolePolicy"
}