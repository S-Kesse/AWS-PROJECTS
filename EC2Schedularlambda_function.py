import boto3
import os
import botocore
from datetime import date
from botocore.exceptions import ClientError

arole = 'EC2Scheduler-Role'

def assume_roles(acc,accounts,arole):
    global acc_key
    global sec_key
    global sess_tok
    global client
    sts_conn = boto3.client('sts')
    tmp_arn = f"{acc}:role/{arole}"
    try:
        response = sts_conn.assume_role(DurationSeconds=900,RoleArn=f"arn:aws:iam::{tmp_arn}",RoleSessionName='EC2Scheduler')
        acc_key = response['Credentials']['AccessKeyId']
        sec_key = response['Credentials']['SecretAccessKey']
        sess_tok = response['Credentials']['SessionToken']
    except botocore.exceptions.ClientError as e:
        print(f"Error while processing account {acc} ")
        print(e.response['Error']['Message'])   



def lambda_handler(event, context):
    print("--- Start of Execution ---")
    print("\n \n \n EC2 Scheduler processing ...")   
    global ec2
    global session
    global client
  
    #Init variable
    
    region_list = 'us-east-1,us-west-2,ca-central-1'
    #region_list = 'us-east-1'
    regions=region_list.split(",")
    account_list = '976369463007,597993423533,036615378632,239656608637,168793161457,417048159015,143514109062,967714306747,653782111221,891712817618,928642811045,912288852094,294566486939,658279452225,354582679613'
    #account_list = '928642811045'
    accounts = account_list.split(",")
    
    operation=event['operation']
    timezone=event['timezone']
    print(f'Executing -{operation}- operation on EC2 instances in {timezone} timezone.')
    #assume cross account role and processing
    client = boto3.client("sts")

    for reg in regions:
        for acc in accounts:
            print(f"Processing account: {acc} ({reg})")
            #getting instances informations
            try:
                assume_roles(acc,accounts,arole)                    
                ec2 = boto3.client('ec2',aws_access_key_id=acc_key,aws_secret_access_key=sec_key,aws_session_token=sess_tok,region_name=reg)
                reservations = ec2.describe_instances()
            except botocore.exceptions.ClientError as e:
                print(f"Error while processing account {acc} :")
                print(e.response['Error']['Message'])   
             
            instances = []
            for reservation in reservations.get('Reservations', []):
                for instance in reservation.get('Instances', []):
                    instances.append(instance)
            #process data for each instance
            for i in range(len(instances)):
                StoppedByScheduler='no'
                Managed='no'
                SchedulerTimeZone=''
                InstanceName=''
                InstanceId=instances[i]['InstanceId']
                State=instances[i]['State']['Name']
                try:
                    Tags=instances[i]['Tags']
                    for ii in range(len(Tags)):
                        if Tags[ii]['Key'] == 'EC2Scheduler_TimeZone':
                            Managed='yes'
                            SchedulerTimeZone=Tags[ii]['Value']
                        if Tags[ii]['Key'] == 'EC2Scheduler_State' and Tags[ii]['Value'] == 'Stopped':
                            StoppedByScheduler = 'yes'
                        if Tags[ii]['Key'] == 'Name':
                            InstanceName=Tags[ii]['Value']
                    #Tags_str=str(Tags)
                    #if 'EC2Scheduler_State' not in Tags_str:
                    #        StoppedByScheduler='yes'

                        
                    
                    #execute operation if managed instance 
                    if Managed == 'yes' and operation == 'stop' and SchedulerTimeZone == timezone and State == 'running':
                        ec2.create_tags(
                            Resources=[InstanceId],
                            Tags=[
                                    {
                                        'Key': 'EC2Scheduler_State',
                                        'Value':'Stopped'
                                    }
                                ]
                            )
                        ec2.stop_instances(
                            InstanceIds=[InstanceId]
                            )
                        print (f"Instance stopped {InstanceId} - {InstanceName}")
    
                    if Managed == 'yes' and operation == 'start' and SchedulerTimeZone == timezone and State == 'stopped' and StoppedByScheduler == 'yes':
                        ec2.create_tags(
                            Resources=[InstanceId],
                            Tags=[
                                    {
                                        'Key': 'EC2Scheduler_State',
                                        'Value':'Started'
                                    }
                                ]
                            )
                        ec2.start_instances(
                            InstanceIds=[InstanceId]
                            )
                        print (f"Instance started {InstanceId} - {InstanceName}")
                            
                    #print(f" Instance processed {InstanceId} - {State} - Managed : {Managed} - {SchedulerTimeZone}")
                except Exception as e:   
                    print(f"Error while processing instance {InstanceId} :")
                    print(e)       

    
    print("--- End of Execution ")

