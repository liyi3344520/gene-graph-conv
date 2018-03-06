import argparse
import logging
import tensorflow as tf  # necessary to import here to avoid segfault
import datasets
import models
import torch
import time
from torch.autograd import Variable
import monitoring
from metrics import record_metrics_for_epoch, summarize


def build_parser():
    parser = argparse.ArgumentParser(
        description="Model for convolution-graph network (CGN)")

    parser.add_argument('--epoch', default=10, type=int, help='The number of epochs we want ot train the network.')
    parser.add_argument('--seed', default=1993, type=int, help='Seed for random initialization and stuff.')
    parser.add_argument('--batch-size', default=100, type=int, help="The batch size.")
    parser.add_argument('--tensorboard-dir', default='./experiments/', help='The folder where to store the experiments. Will be created if not already exists.')
    parser.add_argument('--lr', default=1e-3, type=float, help='learning rate')
    parser.add_argument('--weight-decay', default=0., type=float, help='weight decay (L2 loss).')
    parser.add_argument('--l1-loss-lambda', default=0., type=float, help='L1 loss lambda.')
    parser.add_argument('--momentum', default=0.9, type=float, help='momentum')
    parser.add_argument('--dataset', choices=['random', 'tcga-tissue', 'tcga-brca', 'tcga-label', 'tcga-gbm', 'percolate', 'nslr-syn', 'percolate-plus'],
                        default='random', help='Which dataset to use.')
    parser.add_argument('--clinical-file', type=str, default='PANCAN_clinicalMatrix.gz', help='File to read labels from')
    parser.add_argument('--clinical-label', type=str, default='gender', help='Label to join with data')
    parser.add_argument('--scale-free', action='store_true', help='If we want a scale-free random adjacency matrix for the dataset.')
    parser.add_argument('--cuda', action='store_true', help='If we want to run on gpu.')
    parser.add_argument('--norm-adj', default=True, type=bool, help="If we want to normalize the adjancy matrix.")
    parser.add_argument('--log', choices=['console', 'silent'], default='console', help="Determines what kind of logging you get")
    parser.add_argument('--name', type=str, default=None, help="If we want to add a random str to the folder.")

    # Model specific options
    parser.add_argument('--num-channel', default=32, type=int, help='Number of channel in the model.')
    parser.add_argument('--dropout', default=False, type=bool, help='If we want to perform dropout in the model..')
    parser.add_argument('--model', default='cgn', choices=['cgn', 'mlp', 'lcg', 'sgc', 'slr', 'cnn', 'random'], help='Number of channel in the CGN.')
    parser.add_argument('--experiment-var', type=str, default='na', help='var that we are experimenting on, used for dir name.')
    parser.add_argument('--trial-number', type=str, default='1', help='the trial number of the experiment.')
    parser.add_argument('--num-layer', default=1, type=int, help='Number of convolution layer in the CGN.')
    parser.add_argument('--nb-class', default=None, type=int, help="Number of class for the dataset (won't work with random graph).")
    parser.add_argument('--nb-examples', default=10000, type=int, help="Number of samples to train on.")
    parser.add_argument('--nb-per-class', default=None, type=int, help="Number of samples per class.")
    parser.add_argument('--train-ratio', default=0.6, type=float, help="The ratio of data to be used in the training set.")
    parser.add_argument('--percentile', default=100, type=float, help="How many edges to keep.")
    parser.add_argument('--add-self', default=True, type=bool, help="Add self references in the graph.")
    parser.add_argument('--attention-layer', default=0, type=int, help="The number of attention layer to add to the last layer. Only implemented for CGN.")
    parser.add_argument('--pool-graph', default=None, choices=['ignore', 'hierarchy'], help="If we want to pool the graph.")
    parser.add_argument('--use-emb', default=None, type=int, help="If we want to add node embeddings.")
    parser.add_argument('--use-gate', default=0., type=float, help="The lambda for the gate pooling/striding. is ignore if = 0.")
    parser.add_argument('--model_reg_lambda', default=0.0, type=float, nargs='*', help="A lambda for the regularization on a specific model.")
    parser.add_argument('--size-perc', default=4, type=int, help="The size of the connected percolate graph in percolate-plus datsaet")
    parser.add_argument('--extra-cn', default=0, type=int, help="The number of extra nodes with edges in the percolate-plus dataset.")
    parser.add_argument('--extra-ucn', default=0, type=int, help="The number of extra nodes without edges in the percolate-plus dataset")
    parser.add_argument('--disconnected', default=0, type=int, help="The number of disconnected nodes from the perc subgraph without edges in percolate-plus")
    parser.add_argument('--center', default=False, type=bool, help="center the data (subtract mean from each element)?")
<<<<<<< HEAD
    parser.add_argument('--graph-path', default="", type=str, help="path to the graph")
=======
>>>>>>> 192442c5e09ead352c87cce530890c163ab4ca55
    return parser


def parse_args(argv):
    if type(argv) == list or argv is None:
        opt = build_parser().parse_args(argv)
    else:
        opt = argv
    return opt


def setup_logger(opt):
    logging.basicConfig(format="%(message)s")
    logger = logging.getLogger()
    if opt.log != 'silent':
        logger.setLevel('INFO')


def main(argv=None):
    opt = parse_args(argv)
    setup_logger(opt)
    logging.info(vars(opt))
    if opt.cuda:
        torch.cuda.manual_seed(opt.seed)
        torch.cuda.manual_seed_all(opt.seed)
    torch.manual_seed(opt.seed)

    logging.info("Getting the dataset...")
    dataset = datasets.get_dataset(opt)

    train_set, valid_set, test_set = datasets.split_dataset(dataset, batch_size=opt.batch_size, seed=opt.seed,
                                                            nb_samples=opt.nb_examples, train_ratio=opt.train_ratio, nb_per_class=opt.nb_per_class)

    logging.info("Getting the model...")
    my_model = models.get_model(opt, dataset)

    logging.info("Our model:")
    logging.info(my_model)

    # Setup the loss
    criterion = torch.nn.CrossEntropyLoss(size_average=True)
    l1_criterion = torch.nn.L1Loss(size_average=False)
    optimizer = torch.optim.Adam(my_model.parameters(), lr=opt.lr, weight_decay=opt.weight_decay)

    if opt.cuda:
        logging.info("Putting the model on gpu...")
        my_model.cuda()

    writer, exp_dir = monitoring.setup_tensorboard_log(opt)

    max_valid = 0
    best_summary = {}
    patience = 20

    # The training.
    for t in range(opt.epoch):

        start_timer = time.time()

        for no_b, mini in enumerate(train_set):

            inputs, targets = mini['sample'], mini['labels']

            inputs = Variable(inputs, requires_grad=False).float()
            targets = Variable(targets, requires_grad=False).long()

            if opt.cuda:
                inputs = inputs.cuda()
                targets = targets.cuda()

            # Forward pass: Compute predicted y by passing x to the model
            y_pred = my_model(inputs).float()

            # Compute and print loss
            cross_loss = criterion(y_pred, targets)
            model_regularization_loss = my_model.regularization(opt.model_reg_lambda)
            l1_loss = models.setup_l1_loss(my_model, opt.l1_loss_lambda, l1_criterion, opt.cuda)
            total_loss = cross_loss + model_regularization_loss + l1_loss

            # Zero gradients, perform a backward pass, and update the weights.
            optimizer.zero_grad()
            total_loss.backward()
            optimizer.step()

        time_this_epoch = time.time() - start_timer

        acc, auc = record_metrics_for_epoch(writer, cross_loss, total_loss, t, time_this_epoch, train_set, valid_set, test_set, my_model, dataset, opt)

        summary = [
            t,
            cross_loss.data[0],
            total_loss.data[0],
            acc['train'],
            acc['valid'],
            auc['train'],
            auc['valid'],
            time_this_epoch
        ]
        summary = "epoch {}, cross_loss: {:.03f}, acc_train: {:0.3f}, acc_valid: {:0.3f}, auc_train: {:0.3f}, auc_valid:{:0.3f}, time: {:.02f} sec".format(*summary)
        logging.info(summary)

        patience = patience - 1
        if patience == 0:
            break
        if max_valid < auc['valid'] and t > 5:
            max_valid = auc['valid']
            best_summary = summarize(t, cross_loss.data[0], total_loss.data[0], acc, auc)
            patience = 100

    logging.info("Done!")
    monitoring.monitor_everything(my_model, valid_set, opt, exp_dir)
    return best_summary

if __name__ == '__main__':
    main()
