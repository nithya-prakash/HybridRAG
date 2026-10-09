# Random forest

Random forests or random decision forests is an ensemble learning method for classification, regression and other tasks that works by creating a multitude of decision trees during training. For classification tasks, the output of the random forest is the class selected by most trees. For regression tasks, the output is the average of the predictions of the trees. Random forests correct for decision trees' habit of overfitting to their training set.
The first algorithm for random decision forests was created in 1995 by Tin Kam Ho using the random subspace method, which, in Ho's formulation, is a way to implement the "stochastic discrimination" approach to classification proposed by Eugene Kleinberg.
An extension of the algorithm was developed by Leo Breiman and Adele Cutler, who registered "Random Forests" as a trademark in 2006 (as of 2019, owned by Minitab, Inc.). The extension combines Breiman's "bagging" idea and random selection of features, introduced first by Ho and later independently by Amit and Geman in order to construct a collection of decision trees with controlled variance.


## History
The general method of random decision forests was first proposed by Salzberg and Heath in 1993, with a method that used a randomized decision tree algorithm to create multiple trees and then combine them using majority voting.  This idea was developed further by Ho in 1995.  Ho established that forests of trees splitting with oblique hyperplanes can gain accuracy as they grow without suffering from overtraining, as long as the forests are randomly restricted to be sensitive to only selected feature dimensions.  A subsequent work along the same lines concluded that other splitting methods behave similarly, as long as they are randomly forced to be insensitive to some feature dimensions.  This observation that a more complex classifier (a larger forest) gets more accurate nearly monotonically is in sharp contrast to the common belief that the complexity of a classifier can only grow to a certain level of accuracy before being hurt by overfitting.  The explanation of the forest method's resistance to overtraining can be found in Kleinberg's theory of stochastic discrimination.
The early development of Breiman's notion of random forests was influenced by the work of Amit and Geman who introduced the idea of searching over a random subset of the available decisions when splitting a node, in the context of growing a single tree.  The idea of random subspace selection from Ho was also influential in the design of random forests.  This method grows a forest of trees, and introduces variation among the trees by projecting the training data into a randomly chosen subspace before fitting each tree or each node.  Finally, the idea of randomized node optimization, where the decision at each node is selected by a randomized procedure, rather than a deterministic optimization was first introduced by Thomas G. Dietterich.
The proper introduction of random forests was made in a paper by Leo Breiman,
that has become one of the world's most cited papers.
This paper describes a method of building a forest of uncorrelated trees using a CART-like procedure, combined with randomized node optimization and bagging.  In addition, this paper combines several ingredients, some previously known and some novel, which form the basis of the modern practice of random forests, in particular:

Using out-of-bag error as an estimate of the generalization error.
Measuring variable importance through permutation.
The report also offers the first theoretical result for random forests in the form of a bound on the generalization error which depends on the strength of the trees in the forest and their correlation.


## Algorithm


## Preliminaries: decision tree learning

Decision trees are a popular method for various machine learning tasks. Tree learning is almost "an off-the-shelf procedure for data mining", say Hastie et al., "because it is invariant under scaling and various other transformations of feature values, is robust to inclusion of irrelevant features, and produces inspectable models. However, they are seldom accurate".
In particular, trees that are grown very deep tend to learn highly irregular patterns: they overfit their training sets, i.e. have low bias, but very high variance. Random forests are a way of averaging multiple deep decision trees, trained on different parts of the same training set, with the goal of reducing the variance. This comes at the expense of a small increase in the bias and some loss of interpretability, but generally greatly boosts the performance in the final model.


## Bagging

The training algorithm for random forests applies the general technique of bootstrap aggregating, or bagging, to tree learners. Given a training set X = x1, ..., xn with responses Y = y1, ..., yn, bagging repeatedly (B times) selects a random sample with replacement of the training set and fits trees to these samples:

After training, predictions for unseen samples x' can be made by averaging the predictions from all the individual regression trees on x':

  
    
      
        
          
            
              f
              ^
            
          
        
        =
        
          
            1
            B
          
        
        
          ∑
          
            b
            =
            1
          
          
            B
          
        
        
          f
          
            b
          
        
        (
        
          x
          ′
        
        )
      
    
    {\displaystyle {\hat {f}}={\frac {1}{B}}\sum _{b=1}^{B}f_{b}(x')}
  

or by taking the plurality vote in the case of classification trees.
This bootstrapping procedure leads to better model performance because it decreases the variance of the model, without increasing the bias. This means that while the predictions of a single tree are highly sensitive to noise in its training set, the average of many trees is not, as long as the trees are not correlated. Simply training many trees on a single training set would give strongly correlated trees (or even the same tree many times, if the training algorithm is deterministic); bootstrap sampling is a way of de-correlating the trees by showing them different training sets.
Additionally, an estimate of the uncertainty of the prediction can be made as the standard deviation of the predictions from all the individual regression trees on x′:

  
    
      
        σ
        =
        
          
            
              
                
                  ∑
                  
                    b
                    =
                    1
                  
                  
                    B
                  
                
                (
                
                  f
                  
                    b
                  
                
                (
                
                  x
                  ′
                
                )
                −
                
                  
                    
                      f
                      ^
                    
                  
                
                
                  )
                  
                    2
                  
                
              
              
                B
                −
                1
              
            
          
        
        .
      
    
    {\displaystyle \sigma ={\sqrt {\frac {\sum _{b=1}^{B}(f_{b}(x')-{\hat {f}})^{2}}{B-1}}}.}
  

The number B of samples (equivalently, of trees) is a free parameter. Typically, a few hundred to several thousand trees are used, depending on the size and nature of the training set. B can be optimized using cross-validation, or by observing the out-of-bag error: the mean prediction error on each training sample xi, using only the trees that did not have xi in their bootstrap sample.
The training and test error tend to level off after some number of trees have been fit.


## From bagging to random forests

The above procedure describes the original bagging algorithm for trees. Random forests also include another type of bagging scheme: they use a modified tree learning algorithm that selects, at each candidate split in the learning process, a random subset of the features. This process is sometimes called "feature bagging". The reason for doing this is the correlation of the trees in an ordinary bootstrap sample: if one or a few features are very strong predictors for the response variable (target output), these features will be selected in many of the B trees, causing them to become correlated. An analysis of how bagging and random subspace projection contribute to accuracy gains under different conditions is given by Ho.
Typically, for a classification problem with 
  
    
      
        p
      
    
    {\displaystyle p}
  
 features, 
  
    
      
        
          
            p
          
        
      
    
    {\displaystyle {\sqrt {p}}}
  
 (rounded down) features are used in each split.  For regression problems the inventors recommend 
  
    
      
        p
        
          /
        
        3
      
    
    {\displaystyle p/3}
  
 (rounded down) with a minimum node size of 5 as the default. In practice, the best values for these parameters should be tuned on a case-to-case basis for every problem.


## ExtraTrees
Adding one further step of randomization yields extremely randomized trees, or ExtraTrees. As with ordinary random forests, they are an ensemble of individual trees, but there are two main differences: (1) each tree is trained using the whole learning sample (rather than a bootstrap sample), and (2) the top-down splitting is randomized: for each feature under consideration, a number of random cut-points are selected, instead of computing the locally optimal cut-point (based on, e.g., information gain or the Gini impurity). The values are chosen from a uniform distribution within the feature's empirical range (in the tree's training set). Then, of all the randomly chosen splits, the split that yields the highest score is chosen to split the node.
Similar to ordinary random forests, the number of randomly selected features to be considered at each node can be specified. Default values for this parameter are 
  
    
      
        
          
            p
          
        
      
    
    {\displaystyle {\sqrt {p}}}
  
 for classification and 
  
    
      
        p
      
    
    {\displaystyle p}
  
 for regression, where 
  
    
      
        p
      
    
    {\displaystyle p}
  
 is the number of features in the model.


## Random forests for high-dimensional data
The basic random forest procedure may not work well in situations where there are a large number of features but only a small proportion of these features are informative with respect to sample classification. This can be addressed by encouraging the procedure to focus mainly on features and trees that are informative. Some methods for accomplishing this are:

Prefiltering: Eliminate features that are mostly just noise.
Enriched Random Forest (ERF): Use weighted random sampling instead of simple random sampling at each node of each tree, giving greater weight to features that appear to be more informative.
Tree-weighted random forest (TWRF): Give more weight to more accurate trees.


## Properties


## Variable importance
Random forests can be used to rank the importance of variables in a regression or classification problem in a natural way.  The following technique was described in Breiman's original paper and is implemented in the R package randomForest.


## Permutation importance
To measure a feature's importance in a data set 
  
    
      
        
          
            
              D
            
          
          
            n
          
        
        =
        {
        (
        
          X
          
            i
          
        
        ,
        
          Y
          
            i
          
        
        )
        
          }
          
            i
            =
            1
          
          
            n
          
        
      
    
    {\displaystyle {\mathcal {D}}_{n}=\{(X_{i},Y_{i})\}_{i=1}^{n}}
  
, first a random forest is trained on the data.  During training, the out-of-bag error for each data point is recorded and averaged over the forest. (If bagging is not used during training, we can instead compute errors on an independent test set.)
After training, the values of the feature are permuted in the out-of-bag samples and the out-of-bag error is again computed on this perturbed data set. The importance for the feature is computed by averaging the difference in out-of-bag error before and after the permutation over all trees.  The score is normalized by the standard deviation of these differences.
Features which produce large values for this score are ranked as more important than features which produce small values. The statistical definition of the variable importance measure was given and analyzed by Zhu et al.
This method of determining variable importance has some drawbacks:

When features have different numbers of values, random forests favor features with more values. Solutions to this problem include partial permutations and growing unbiased trees.
If the data contain groups of correlated features of similar relevance, then smaller groups are favored over large groups.
If there are collinear features, the procedure may fail to identify important features. A solution is to permute groups of correlated features together.


## Mean decrease in impurity feature importance
This approach to feature importance for random forests considers as important the variables which decrease a lot the impurity during splitting. It is described in the book Classification and Regression Trees by Leo Breiman and is the default implementation in scikit learn and R. The definition is:
  
    
      
        
          unormalized average importance
        
        (
        x
        )
        =
        
          
            1
            
              n
              
                T
              
            
          
        
        
          ∑
          
            i
            =
            1
          
          
            
              n
              
                T
              
            
          
        
        
          ∑
          
            
              node 
            
            j
            ∈
            
              T
              
                i
              
            
            
              |
            
            
              split variable
            
            (
            j
            )
            =
            x
          
        
        
          p
          
            
              T
              
                i
              
            
          
        
        (
        j
        )
        Δ
        
          i
          
            
              T
              
                i
              
            
          
        
        (
        j
        )
        ,
      
    
    {\displaystyle {\text{unormalized average importance}}(x)={\frac {1}{n_{T}}}\sum _{i=1}^{n_{T}}\sum _{{\text{node }}j\in T_{i}|{\text{split variable}}(j)=x}p_{T_{i}}(j)\Delta i_{T_{i}}(j),}
  
where 

  
    
      
        x
      
    
    {\displaystyle x}
  
 is a feature

  
    
      
        
          n
          
            T
          
        
      
    
    {\displaystyle n_{T}}
  
 is the number of trees in the forest

  
    
      
        
          T
          
            i
          
        
      
    
    {\displaystyle T_{i}}
  
 is tree 
  
    
      
        i
      
    
    {\displaystyle i}
  

  
    
      
        
          p
          
            
              T
              
        