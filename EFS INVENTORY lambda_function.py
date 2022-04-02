import boto3
import os
import csv
import botocore
from datetime import date
from datetime import datetime
from dateutil.relativedelta import relativedelta
from botocore.exceptions import ClientError
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication



     


def lambda_handler(event, context):
    print("--- Start of Execution ---")
    global ec2
    global session
    global client
  
    #Init variable
    tmp_file='/tmp/efsinventory.csv'
    dt=date.today()
    dtstr=dt.strftime("%Y-%d-%m")
    s3_output_file='EFS-Inventory-'+dtstr+'.csv'
    s3_bucket='org-894835236266-us-east-1-centralized-efsinventoryreports-dev'
    region_list = 'us-east-1,us-west-2,ca-central-1'
    #region_list = 'us-east-1'
    regions=region_list.split(",")
    SUBJECT='EFS Inventory Reports - '+dtstr
    SENDER='noreply@mitchell-aws.awsapps.com'
    RECIPIENT = event['EMAIL']
    BODY_TEXT='Please find attached EFS Inventory for '+dtstr
    sts_conn = boto3.client('sts')
    arole = 'EFSInventory-Role'
    
    #writing cs_headers
    with open(tmp_file, 'w',encoding='UTF8',newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['Region','AccountId','AccountName','FileSystemId','FileSystemName','CreationTime','LifeCycleState','SizeInBytes','Encrypted','KmsKeyId','ThroughputMode','ProvisionedThroughputInMibps','AvailabilityZoneName','AvailabilityZoneId','IpAddresses','Tags'])
    

    #getting org accounts id and names
    org = boto3.client("organizations")
    response=org.list_accounts()
    act_lst=response['Accounts']
    while "NextToken" in response:
        response=org.list_accounts(
            NextToken=response["NextToken"]
            )
        act_lst.extend(response['Accounts'])
    #getting account id list
    accounts=[]
    for i in range(len(act_lst)):
        current_account=act_lst[i]['Id']
        accounts.append(current_account)
        
    #accounts=['778111445197','800678780575']
    
    for reg in regions:
        for acc in accounts:
            #Getting account name
            for i in range(len(act_lst)):
                if acc == act_lst[i]['Id']:
                    acc_name = act_lst[i]['Name']
            
            print(f"Processing account {acc} {acc_name}  ({reg})")

            try:
                #assume_roles(acc,arole)
                tmp_arn = f"{acc}:role/{arole}"
                response = sts_conn.assume_role(DurationSeconds=900,RoleArn=f"arn:aws:iam::{tmp_arn}",RoleSessionName='EFSInventory')
                acc_key = response['Credentials']['AccessKeyId']
                sec_key = response['Credentials']['SecretAccessKey']
                sess_tok = response['Credentials']['SessionToken']
                efs_client = boto3.client('efs',aws_access_key_id=acc_key,aws_secret_access_key=sec_key,aws_session_token=sess_tok,region_name=reg)
                
                #getting EFS informations
                response=efs_client.describe_file_systems()
                efs_list=response['FileSystems']
                while "NextMarker" in response:
                    response=efs_client.describe_file_systems(
                        Marker=response["NextMarker"]
                        )
                    efs_list.extend(response['FileSystems'])




                #Process EFS List - Gathering informations
                for i in range(len(efs_list)):
                    FileSystemId=efs_list[i]['FileSystemId']
                    OwnerId=efs_list[i]['OwnerId']
                    CreationTime=efs_list[i]['CreationTime']
                    CreationTime=datetime.strftime(CreationTime,"%Y-%m-%d %H:%M:%S")
                    LifeCycleState=efs_list[i]['LifeCycleState']
                    Name=efs_list[i]['Name']
                    SizeInBytes=efs_list[i]['SizeInBytes']['Value']
                    PerformanceMode=efs_list[i]['PerformanceMode']
                    Encrypted=efs_list[i]['Encrypted']
                    ThroughputMode=efs_list[i]['ThroughputMode']
                    KmsKeyId=''
                    ProvisionedThroughputInMibps=''
                    AvailabilityZoneName=''
                    AvailabilityZoneId=''
                    Tags=''
       
                    if 'KmsKeyId' in efs_list[i]:
                        KmsKeyId=efs_list[i]['KmsKeyId']
                    
                    if 'ProvisionedThroughputInMibps' in efs_list[i]:
                        ProvisionedThroughputInMibps=efs_list[i]['ProvisionedThroughputInMibps']
                    
                    if 'AvailabilityZoneName' in efs_list[i]:
                        AvailabilityZoneName=efs_list[i]['AvailabilityZoneName']
                    
                    if 'AvailabilityZoneId' in efs_list[i]:
                        AvailabilityZoneId=efs_list[i]['AvailabilityZoneId']
                    
                    if 'Tags' in efs_list[i]:
                        Tags=efs_list[i]['Tags']
                        
                    #getting EFS Mount targets informations
                    response=efs_client.describe_mount_targets(
                        FileSystemId=FileSystemId
                        )
                    mt_list=response['MountTargets']
                    
                    while "NextMarker" in response:
                        response=efs_client.describe_mount_targets(
                            Marker=response["NextMarker"],
                            FileSystemId=FileSystemId
                            )
                        mt_list.extend(response['MountTargets'])                    
                    IpAddresses=[]
                    for ii in range(len(mt_list)):
                        if FileSystemId == mt_list[ii]['FileSystemId']:
                            IpAddresses.append(mt_list[ii]['IpAddress'])
                            
                    #print(IpAddresses)
                    
                    #print(f"{reg} {acc} {acc_name} {FileSystemId} {Name} {CreationTime} {LifeCycleState}  {SizeInBytes} {Encrypted} {KmsKeyId} {ThroughputMode} {ProvisionedThroughputInMibps} {AvailabilityZoneName} {AvailabilityZoneId}")
     
                    #writing csv row
                    with open(tmp_file, 'a',encoding='UTF8',newline='') as csvfile:
                    #csvfile= open (tmp_file,"a")
                        writer = csv.writer(csvfile)
                        writer.writerow([reg,acc,acc_name,FileSystemId,Name,CreationTime,LifeCycleState,SizeInBytes,Encrypted,KmsKeyId,ThroughputMode,ProvisionedThroughputInMibps,AvailabilityZoneName,AvailabilityZoneId,IpAddresses,Tags])

            except Exception as e:
                print(f"Error while processing account {acc} :")
                print(e)

              

    #upload to s3
    print(f"Uploading {s3_output_file} to S3 Bucket : {s3_bucket}")
    s3=boto3.client("s3")
    s3.upload_file(tmp_file, s3_bucket, s3_output_file)
    
    #formatting file name for SES
    #s3_output_file=s3_output_file.split("/")
    #s3_output_file=s3_output_file[1]
    
    #building SES msg
    msg = MIMEMultipart()
    msg['Subject'] = SUBJECT
    msg['From'] = SENDER
    msg['To'] = RECIPIENT
    textpart = MIMEText(BODY_TEXT)
    msg.attach(textpart)    
    att = MIMEApplication(open(tmp_file, 'rb').read())
    att.add_header('Content-Disposition','attachment',filename=s3_output_file)
    msg.attach(att)
    #sending email
    ses=boto3.client('ses')
    print(f"Sending email to {RECIPIENT}")
    try:
        response = ses.send_raw_email(
            Source=SENDER,
            Destinations=[RECIPIENT],
            RawMessage={ 'Data':msg.as_string() }
        )
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        print("Email sent! Message ID:",response['MessageId'])


    print("--- End of Execution ---")
