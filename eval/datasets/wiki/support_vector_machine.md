# Support vector machine

In machine learning, a support vector machine (SVM) or support vector network is a supervised max-margin model with associated learning algorithms that analyze data for classification and regression analysis. Developed at AT&T Bell Laboratories, SVMs are one of the most studied models, being based on statistical learning frameworks of VC theory proposed by Vapnik (1982, 1995) and Chervonenkis (1974).
In addition to performing linear classification, SVMs can efficiently perform non-linear classification using the kernel trick, representing the data only through a set of pairwise similarity comparisons between the original data points using a kernel function, thereby transforming them into coordinates in a higher-dimensional feature space. Thus, SVMs use the kernel trick to implicitly map their inputs into high-dimensional feature spaces, where linear classification can be performed. Furthermore, the computational complexity arising from using the kernel trick warrants lesser usage of resources. As members of the max-margin models, SVMs are resilient to noisy data (e.g., misclassified examples). They can also be used for regression tasks, where the objective becomes 
  
    
      
        ϵ
      
    
    {\displaystyle \epsilon }
  
-sensitive.
The support vector clustering algorithm, created by Hava Siegelmann and Vladimir Vapnik, applies the statistics of support vectors, developed in the support vector machines algorithm, to categorize unlabelled data. These data sets require unsupervised learning approaches, which attempt to find natural clustering of the data into groups, and then to map new data according to these clusters.
The popularity of SVMs is likely due to their amenability to theoretical analysis and their flexibility in being applied to a wide variety of tasks, including structured prediction problems. It is not clear that SVMs have better predictive performance than other linear models, such as logistic regression and linear regression.


## Motivation

Classifying data is a common task in machine learning. Say we have a binary classification problem: suppose some given data points each belong to one of two classes, and the goal is to decide which class a new data point will be in. In the case of support vector machines, a data point is viewed as a 
  
    
      
        p
      
    
    {\displaystyle p}
  
-dimensional vector (a list of 
  
    
      
        p
      
    
    {\displaystyle p}
  
 numbers), and we want to know whether we can separate such points with a 
  
    
      
        (
        p
        −
        1
        )
      
    
    {\displaystyle (p-1)}
  
-dimensional hyperplane. This is called a linear classifier. There are many hyperplanes that might classify the data. One reasonable choice as the best hyperplane is the one that represents the largest separation, or margin, between the two classes. Therefore, we choose a hyperplane such that its distance from the data points nearest to it on each side is maximized. If such a hyperplane exists, it is known as the maximum-margin hyperplane and the linear classifier it defines is known as a maximum-margin classifier; or equivalently, the perceptron of optimal stability.
More formally, a support vector machine constructs a hyperplane or set of hyperplanes in a high or infinite-dimensional space, which can be used for classification, regression, or other tasks like outlier detection. Intuitively, a good separation is achieved by the hyperplane that has the largest distance to the nearest training-data point of any class (so-called functional margin), since in general the larger the margin, the lower the generalization error of the classifier. A lower generalization error means that the implementer is less likely to experience overfitting.
Whereas the original problem may be stated in a finite-dimensional space, it often happens that the sets to discriminate are not linearly separable in that space. For this reason, it was proposed that the original finite-dimensional space be mapped into a much higher-dimensional space, presumably making the separation easier in that space. To keep the computational load reasonable, the mappings used by SVM schemes are designed to ensure that dot products of pairs of input data vectors may be computed easily in terms of the variables in the original space, by defining them in terms of a kernel function 
  
    
      
        k
        (
        x
        ,
        y
        )
      
    
    {\displaystyle k(x,y)}
  
 selected to suit the problem. The hyperplanes in the higher-dimensional space are defined as the set of points whose dot product with a vector in that space is constant, where such a set of vectors is an orthogonal (and thus minimal) set of vectors that defines a hyperplane. The vectors defining the hyperplanes can be chosen to be linear combinations with parameters 
  
    
      
        
          α
          
            i
          
        
      
    
    {\displaystyle \alpha _{i}}
  
 of images of feature vectors 
  
    
      
        
          x
          
            i
          
        
      
    
    {\displaystyle x_{i}}
  
 that occur in the data base. With this choice of a hyperplane, the points 
  
    
      
        x
      
    
    {\displaystyle x}
  
 in the feature space that are mapped into the hyperplane are defined by the relation 
  
    
      
        
          
            ∑
            
              i
            
          
          
            α
            
              i
            
          
          k
          (
          
            x
            
              i
            
          
          ,
          x
          )
          =
          
            constant
          
          .
        
      
    
    {\displaystyle \textstyle \sum _{i}\alpha _{i}k(x_{i},x)={\text{constant}}.}
  
  Note that if 
  
    
      
        k
        (
        x
        ,
        y
        )
      
    
    {\displaystyle k(x,y)}
  
 becomes small as 
  
    
      
        y
      
    
    {\displaystyle y}
  
 grows further away from 
  
    
      
        x
      
    
    {\displaystyle x}
  
, each term in the sum measures the degree of closeness of the test point 
  
    
      
        x
      
    
    {\displaystyle x}
  
 to the corresponding data base point 
  
    
      
        
          x
          
            i
          
        
      
    
    {\displaystyle x_{i}}
  
. In this way, the sum of kernels above can be used to measure the relative nearness of each test point to the data points originating in one or the other of the sets to be discriminated. Note the fact that the set of points 
  
    
      
        x
      
    
    {\displaystyle x}
  
 mapped into any hyperplane can be quite convoluted as a result, allowing much more complex discrimination between sets that are not convex at all in the original space.


## Applications
SVMs can be used to solve various real-world problems:

SVMs are helpful in text and hypertext categorization, as their application can significantly reduce the need for labeled training instances in both the standard inductive and transductive settings. Some methods for shallow semantic parsing are based on support vector machines.
Classification of images can also be performed using SVMs. Experimental results show that SVMs achieve significantly higher search accuracy than traditional query refinement schemes after just three to four rounds of relevance feedback. This is also true for image segmentation systems, including those using a modified version SVM that uses the privileged approach as suggested by Vapnik.
Classification of satellite data like SAR data using supervised SVM.
Hand-written characters can be recognized using SVM.
The SVM algorithm has been widely applied in the biological and other sciences.  They have been used to classify proteins with up to 90% of the compounds classified correctly. Permutation tests based on SVM weights have been suggested as a mechanism for interpretation of SVM models. Support vector machine weights have also been used to interpret SVM models in the past. Posthoc interpretation of support vector machine models in order to identify features used by the model to make predictions is a relatively new area of research with special significance in the biological sciences.


## History
The original SVM algorithm was invented by Vladimir N. Vapnik and Alexey Ya. Chervonenkis in 1964. In 1992, Bernhard Boser, Isabelle Guyon and Vladimir Vapnik suggested a way to create nonlinear classifiers by applying the kernel trick to maximum-margin hyperplanes. The "soft margin" incarnation, as is commonly used in software packages, was proposed by Corinna Cortes and Vapnik in 1993 and published in 1995.


## Linear SVM

We are given a training dataset of 
  
    
      
        n
      
    
    {\displaystyle n}
  
 points of the form

  
    
      
        (
        
          
            x
          
          
            1
          
        
        ,
        
          y
          
            1
          
        
        )
        ,
        …
        ,
        (
        
          
            x
          
          
            n
          
        
        ,
        
          y
          
            n
          
        
        )
        ,
      
    
    {\displaystyle (\mathbf {x} _{1},y_{1}),\ldots ,(\mathbf {x} _{n},y_{n}),}
  

where the 
  
    
      
        
          y
          
            i
          
        
      
    
    {\displaystyle y_{i}}
  
 are either 1 or −1, each indicating the class to which the point 
  
    
      
        
          
            x
          
          
            i
          
        
      
    
    {\displaystyle \mathbf {x} _{i}}
  
 belongs. Each 
  
    
      
        
          
            x
          
          
            i
          
        
      
    
    {\displaystyle \mathbf {x} _{i}}
  
 is a 
  
    
      
        p
      
    
    {\displaystyle p}
  
-dimensional real vector. We want to find the "maximum-margin hyperplane" that divides the group of points 
  
    
      
        
          
            x
          
          
            i
          
        
      
    
    {\displaystyle \mathbf {x} _{i}}
  
 for which 
  
    
      
        
          y
          
            i
          
        
        =
        1
      
    
    {\displaystyle y_{i}=1}
  
 from the group of points for which 
  
    
      
        
          y
          
            i
          
        
        =
        −
        1
      
    
    {\displaystyle y_{i}=-1}
  
, which is defined so that the distance between the hyperplane and the nearest point 
  
    
      
        
          
            x
          
          
            i
          
        
      
    
    {\displaystyle \mathbf {x} _{i}}
  
 from either group is maximized.
Any hyperplane can be written as the set of points 
  
    
      
        
          x
        
      
    
    {\displaystyle \mathbf {x} }
  
 satisfying
  
    
      
        
          
            w
          
          
            
              T
            
          
        
        
          x
        
        −
        b
        =
        0
        ,
      
    
    {\displaystyle \mathbf {w} ^{\mathsf {T}}\mathbf {x} -b=0,}
  
where 
  
    
      
        
          w
        
      
    
    {\displaystyle \mathbf {w} }
  
 is the (not necessarily normalized) normal vector to the hyperplane. This is much like Hesse normal form, except that 
  
    
      
        
          w
        
      
    
    {\displaystyle \mathbf {w} }
  
 is not necessarily a unit vector. The parameter 
  
    
      
        
          
            
              b
              
                ‖
                
                  w
                
                ‖
              
            
          
        
      
    
    {\displaystyle {\tfrac {b}{\|\mathbf {w} \|}}}
  
 determines the offset of the hyperplane from the origin along the normal vector 
  
    
      
        
          w
        
      
    
    {\displaystyle \mathbf {w} }
  
.
The bias may also be defined so that
  
    
      
        
          
            w
          
          
            
              T
            
          
        
        
          x
        
        +
        b
        =
        0.
      
    
    {\displaystyle \mathbf {w} ^{\mathsf {T}}\mathbf {x} +b=0.}
  


## Hard-margin
If the training data is linearly separable, we can select two parallel hyperplanes that separate the two classes of data, so that the distance between them is as large as possible. The region bounded by these two hyperplanes is called the "margin", and the maximum-margin hyperplane is the hyperplane that lies halfway between them. With a normalized or standardized dataset, these hyperplanes can be described by the equations

  
    
      
        
          
            w
          
          
            
              T
            
          
        
        
          x
        
        −
        b
        =
        1
      
    
    {\displaystyle \mathbf {w} ^{\mathsf {T}}\mathbf {x} -b=1}
  
 (anything on or above this boundary is of one class, with label 1)
and

  
    
      
        
          
            w
          
          
            
              T
            
          
        
        
          x
        
        −
        b
        =
        −
        1
      
    
    {\displaystyle \mathbf {w} ^{\mathsf {T}}\mathbf {x} -b=-1}
  
 (anything on or below this boundary is of the other class, with label −1).
Geometrically, the distance between these two hyperplanes is 
  
    
      
        
          
            
              2
              
                ‖
                
                  w
                
                ‖
              
            
          
        
      
    
    {\displaystyle {\tfrac {2}{\|\mathbf {w} \|}}}
  
, so to maximize the distance between the planes we want to minimize 
  
    
      
        ‖
        
          w
        
        ‖
      
    
    {\displaystyle \|\mathbf {w} \|}
  
. The distance is computed using the distance from a point to a plane equation. We also have to prevent data points from falling into the margin, we add the following constraint: for each 
  
    
      
        i
      
    
    {\displaystyle i}
  
 either

  
    
      
        
          
            w
          
          
            
              T
            
          
        
        
          
            x
          
          
            i
          
        
        −
        b
        ≥
        1
        
        ,
        
           if 
        
        
          y
          
            i
          
        
        =
        1
        ,
      
    
    {\displaystyle \mathbf {w} ^{\mathsf {T}}\mathbf {x} _{i}-b\geq 1\,,{\text{ if }}y_{i}=1,}
  

or

  
    
      
        
          
            w
          
          
            
              T
            
          
        
        
          
            x
          
          
            i
          
        
        −
        b
        ≤
        −
        1
        
        ,
        
           if 
        
        
          y
          
            i
          
        
        =
        −
        1.
      
    
    {\displaystyle \mathbf {w} ^{\mathsf {T}}\mathbf {x} _{i}-b\leq -1\,,{\text{ if }}y_{i}=-1.}
  

These constraints state that each data point must lie on the correct side of the margin.
This can be rewritten as

We can put this together to get the optimization problem:

  
    
      
        
          
            
              
              
                
                  
                    minimize
                    
                      
                        w
 