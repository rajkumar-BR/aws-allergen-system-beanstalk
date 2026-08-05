# "Amazon Cognito: User authentication and access management across all
#  35 location branches" - provisioned here to cover that item from the
# architecture proposal. NOTE: the demo Flask app/UI does NOT currently
# enforce a Cognito login (kept out of scope so you can test the AI
# pipeline immediately) - this pool is ready to wire in via
# flask-cognito / API Gateway + a Cognito authorizer when you're ready
# to lock the dashboard down for real restaurant-staff use across the
# 35 branches.
resource "aws_cognito_user_pool" "staff_pool" {
  name = "${local.name_prefix}-staff-pool"

  password_policy {
    minimum_length    = 10
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = false
  }

  tags = local.common_tags
}

resource "aws_cognito_user_pool_client" "staff_pool_client" {
  name         = "${local.name_prefix}-staff-client"
  user_pool_id = aws_cognito_user_pool.staff_pool.id

  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]
}
