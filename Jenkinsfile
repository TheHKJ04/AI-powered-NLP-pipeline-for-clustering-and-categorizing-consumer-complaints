pipeline {
    agent any
    stages {
        stage('Checkout') {
            steps {
                git branch: 'main', url: 'https://github.com/TheHKJ04/complaint-categorization-system.git'
            }
        }
        stage('Build Docker Image') {
            steps {
                script {
                    docker.build("complaint-api:${env.BUILD_ID}")
                }
            }
        }
        stage('Push to ECR') {
            steps {
                sh '''
                aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin <your-account-id>.dkr.ecr.ap-south-1.amazonaws.com
                docker tag complaint-api:${BUILD_ID} <your-account-id>.dkr.ecr.ap-south-1.amazonaws.com/complaint-api:latest
                docker push <your-account-id>.dkr.ecr.ap-south-1.amazonaws.com/complaint-api:latest
                '''
            }
        }
        stage('Deploy to EC2') {
            steps {
                sh '''
                ssh -o StrictHostKeyChecking=no ec2-user@<EC2-PUBLIC-IP> "docker pull <your-account-id>.dkr.ecr.ap-south-1.amazonaws.com/complaint-api:latest && docker run -d -p 8000:8000 complaint-api:latest"
                '''
            }
        }
    }
}
