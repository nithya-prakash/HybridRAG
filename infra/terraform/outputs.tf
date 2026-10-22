output "public_ip" {
  value = aws_eip.app.public_ip
}

output "frontend_url" {
  value = "http://${aws_eip.app.public_ip}:3000"
}

output "api_url" {
  value = "http://${aws_eip.app.public_ip}:8000"
}

output "uploads_bucket" {
  value = aws_s3_bucket.uploads.bucket
}

output "ssm_session_command" {
  value = "aws ssm start-session --target ${aws_instance.app.id} --region ${var.region}"
}
