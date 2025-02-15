import sys,os,argparse,time
import numpy as np
import torch
import utils
from datetime import datetime

tstart=time.time()

# Arguments
parser=argparse.ArgumentParser(description='xxx')
parser.add_argument('--seed',               default=0,              type=int,   help='(default=%(default)d)')
parser.add_argument('--device',             default='cpu',       type=str,   help='gpu id') #'cuda:0'
parser.add_argument('--experiment',         default='gestures_dynamic',       type=str,   #required=True,
                                            choices=['mnist2','mnist5','pmnist','cifar','mixture', 'gestures_dynamic'])
parser.add_argument('--approach',           default='ucb',            type=str,   help='acl')
parser.add_argument('--data_path',          default='../data/',            type=str,   help='gpu id')

# Training parameters
parser.add_argument('--output',             default='',                     type=str,   help='')
parser.add_argument('--checkpoint_dir',     default='../checkpoints/',    type=str,   help='')
parser.add_argument('--nepochs',            default=200,            type=int,   help='')
parser.add_argument('--sbatch',             default=8,             type=int,   help='')
parser.add_argument('--lr',                 default=0.1,           type=float, help='')  # use 0.3 for non-mnist datasets
parser.add_argument('--nlayers',            default=1,              type=int,   help='')
parser.add_argument('--nhid',               default=30,           type=int, help='')
parser.add_argument('--parameter',          default='',             type=str,   help='')

# Dataset parameters
parser.add_argument('--dataset_n_time_samples',          default=4,           type=int, help='number points in path sequence')
parser.add_argument('--dataset_n_observations',          default=3,            type=int,   help='number of observations (XYZ)')
parser.add_argument('--normalize',          default='no',            type=str,   help='path seq is zeroes based on first/middle point')
parser.add_argument('--normalize_dim',          default='no',            type=str,   help='path min/max values is set to its min/max of all XYZ')
## If dataset parameters changed, you may want to update include/data/learning/tmp_dynamic.npy file (delete it, new one will be automatically created)

# UCB HYPER-PARAMETERS
parser.add_argument('--samples',            default='10',           type=int,     help='Number of Monte Carlo samples')
parser.add_argument('--rho',                default='-3',           type=float,   help='Initial rho')
parser.add_argument('--sig1',               default='0.0',          type=float,   help='STD foor the 1st prior pdf in scaled mixture Gaussian')
parser.add_argument('--sig2',               default='6.0',          type=float,   help='STD foor the 2nd prior pdf in scaled mixture Gaussian')
parser.add_argument('--pi',                 default='0.25',         type=float,   help='weighting factor for prior')
parser.add_argument('--arch',               default='mlp',          type=str,     help='Bayesian Neural Network architecture')

parser.add_argument('--resume',          default='no',            type=str,   help='resume?')
parser.add_argument('--sti',             default=0,               type=int,   help='starting task?')

args=parser.parse_args()
utils.print_arguments(args)

########################################################################################################################

#sys.path.append('/home/pierro/UCB/src')

# Seed
np.random.seed(args.seed)
torch.manual_seed(args.seed)
if torch.cuda.is_available():
    torch.cuda.manual_seed(args.seed)
    # torch.backends.cudnn.benchmark = True
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


print('Using device:', args.device)
checkpoint = utils.make_directories(args)
args.checkpoint = checkpoint
print()
'''
args.accuracy = 43
np.save(os.path.join(args.checkpoint,'args'), args)
print("doe", args.checkpoint)
exit()
'''
# Args -- Experiment
if args.experiment=='mnist2':
    from dataloaders import mnist2 as dataloader
elif args.experiment=='mnist5':
    from dataloaders import mnist5 as dataloader
elif args.experiment=='pmnist':
    from dataloaders import pmnist as dataloader
elif args.experiment=='cifar':
    from dataloaders import cifar as dataloader
elif args.experiment=='mixture':
    from dataloaders import mixture as dataloader
elif args.experiment=='gestures':
    from dataloaders import gestures as dataloader
elif args.experiment=='gestures43':
    from dataloaders import gestures43 as dataloader
elif args.experiment=='gestures322':
    from dataloaders import gestures322 as dataloader
elif args.experiment=='gestures2221':
    from dataloaders import gestures2221 as dataloader
elif args.experiment=='gestures2221_dynamic':
    from dataloaders import gestures2221_dynamic as dataloader
elif args.experiment=='gestures_dynamic':
    from dataloaders import gestures_dynamic as dataloader

# Args -- Approach
if args.approach=='ucb':
    from approaches import ucb as approach

# Args -- Network
if args.experiment=='mnist2' or args.experiment=='pmnist' or args.experiment == 'mnist5' or 'gestures' in args.experiment:
    from networks import mlp_ucb as network
else:
    from networks import resnet_ucb as network


########################################################################################################################
print()
print("Starting this run on :")
print(datetime.now().strftime("%Y-%m-%d %H:%M"))

# Load
print('Load data...')
#data,taskcla,inputsize=dataloader.get(data_path='/home/pierro/UCB/test', seed=0)
#data[3]['train']['y']

data,taskcla,inputsize=dataloader.get(data_path=args.data_path, seed=args.seed, args=args)
print('Input size =',inputsize,'\nTask info =',taskcla)
args.num_tasks=len(taskcla)
args.inputsize, args.taskcla = inputsize, taskcla

# Inits
print('Inits...')
model=network.Net(args).to(args.device)


print('-'*100)
appr=approach.Appr(model,args=args)
print('-'*100)

# args.output=os.path.join(args.results_path, datetime.now().strftime("%d-%m-%Y-%H-%M-%S"))
print('-'*100)

if args.resume == 'yes':
    checkpoint = torch.load(os.path.join(args.checkpoint, 'model_{}.pth.tar'.format(args.sti)))
    model.load_state_dict(checkpoint['model_state_dict'])
    model = model.to(device=args.device)
else:
    args.sti = 0



# Loop tasks
acc=np.zeros((len(taskcla),len(taskcla)),dtype=np.float32)
lss=np.zeros((len(taskcla),len(taskcla)),dtype=np.float32)
for t,ncla in taskcla[args.sti:]:
    print('*'*100)
    print('Task {:2d} ({:s})'.format(t,data[t]['name']))
    print('*'*100)

    if args.approach == 'joint':
        # Get data. We do not put it to GPU
        if t==0:
            xtrain=data[t]['train']['x']
            ytrain=data[t]['train']['y']
            xvalid=data[t]['valid']['x']
            yvalid=data[t]['valid']['y']
            task_t=t*torch.ones(xtrain.size(0)).int()
            task_v=t*torch.ones(xvalid.size(0)).int()
            task=[task_t,task_v]
        else:
            xtrain=torch.cat((xtrain,data[t]['train']['x']))
            ytrain=torch.cat((ytrain,data[t]['train']['y']))
            xvalid=torch.cat((xvalid,data[t]['valid']['x']))
            yvalid=torch.cat((yvalid,data[t]['valid']['y']))
            task_t=torch.cat((task_t,t*torch.ones(data[t]['train']['y'].size(0)).int()))
            task_v=torch.cat((task_v,t*torch.ones(data[t]['valid']['y'].size(0)).int()))
            task=[task_t,task_v]
    else:
        # Get data
        xtrain=data[t]['train']['x'].to(args.device)
        ytrain=data[t]['train']['y'].to(args.device)
        xvalid=data[t]['valid']['x'].to(args.device)
        yvalid=data[t]['valid']['y'].to(args.device)
        task=t

    print(xtrain.shape)
    print(ytrain.shape)
    print(xvalid.shape)
    print(yvalid.shape)
    print(args)
    #print(model)
    #print("end@")
    #exit()
    # Train
    appr.train(task,xtrain,ytrain,xvalid,yvalid)
    print('-'*100)

    # Test
    for u in range(t+1):
        xtest=data[u]['test']['x'].to(args.device)
        ytest=data[u]['test']['y'].to(args.device)
        test_loss,test_acc=appr.eval(u,xtest,ytest,debug=True)
        print('>>> Test on task {:2d} - {:15s}: loss={:.3f}, acc={:5.3f}% <<<'.format(u,data[u]['name'],test_loss,100*test_acc))
        acc[t,u]=test_acc
        lss[t,u]=test_loss

    # Save
    print('Save at '+args.checkpoint)
    np.savetxt(os.path.join(args.checkpoint,'{}_{}_{}.txt'.format(args.experiment,args.approach,args.seed)),acc,'%.5f')
    np.save(os.path.join(args.checkpoint,'args'), args)
    #np.save('/home/petr/my_ws/src/teleop_gesture_toolbox/include/third_party/UCB/checkpoints/gestures_dynamic_ucb', a)

utils.print_log_acc_bwt(args, acc, lss)
print('[Elapsed time = {:.1f} h]'.format((time.time()-tstart)/(60*60)))
