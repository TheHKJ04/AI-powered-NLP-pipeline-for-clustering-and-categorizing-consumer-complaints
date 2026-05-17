pipeline {
    agent any
    stages {
        stage('Checkout') {
            steps {
                git branch: 'main', url: 'https://github.com/TheHKJ04/complaint-categorization-system.git'
            }
        }
        stage('Build Backend Image') {
            steps {
                script {
                    docker.build("complaint-api:${env.BUILD_ID}", "./app")
                }
            }
        }
        stage('Build Frontend Image') {
            steps {
                script {
                    docker.build("complaint-frontend:${env.BUILD_ID}", "./frontend")
                }
            }
        }
        stage('Push Images to ECR') {
            steps {
                sh '''
                aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin <your-account-id>.dkr.ecr.ap-south-1.amazonaws.com

                docker tag complaint-api:${BUILD_ID} <your-account-id>.dkr.ecr.ap-south-1.amazonaws.com/complaint-api:latest
                docker push <your-account-id>.dkr.ecr.ap-south-1.amazonaws.com/complaint-api:latest

                docker tag complaint-frontend:${BUILD_ID} <your-account-id>.dkr.ecr.ap-south-1.amazonaws.com/complaint-frontend:latest
                docker push <your-account-id>.dkr.ecr.ap-south-1.amazonaws.com/complaint-frontend:latest
                '''
            }
        }
        stage('Deploy Backend to EC2') {
            steps {
                sh '''
                ssh -o StrictHostKeyChecking=no ec2-user@<BACKEND-EC2-PUBLIC-IP> "
                  docker pull <your-account-id>.dkr.ecr.ap-south-1.amazonaws.com/complaint-api:latest &&
                  docker run -d -p 8000:8000 complaint-api:latest
                "
                '''
            }
        }
        stage('Deploy Frontend to EC2') {
            steps {
                sh '''
                ssh -o StrictHostKeyChecking=no ec2-user@<FRONTEND-EC2-PUBLIC-IP> "
                  docker pull <your-account-id>.dkr.ecr.ap-south-1.amazonaws.com/complaint-frontend:latest &&
                  docker run -d -p 8501:8501 complaint-frontend:latest
                "
                '''
            }
        }
    }
}
