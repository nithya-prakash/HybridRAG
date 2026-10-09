# Gradient boosting

Gradient boosting is a machine learning technique based on boosting in a functional space, where the target is pseudo-residuals instead of residuals as in traditional boosting. It gives a prediction model in the form of an ensemble of weak prediction models, i.e., models that make very few assumptions about the data, which are typically simple decision trees. When a decision tree is the weak learner, the resulting algorithm is called gradient-boosted trees; it usually outperforms random forest. As with other boosting methods, a gradient-boosted trees model is built in stages, but it generalizes the other methods by allowing optimization of an arbitrary differentiable loss function.


## History
The idea of gradient boosting originated in the observation by Leo Breiman that boosting can be interpreted as an optimization algorithm on a suitable cost function. Explicit regression gradient boosting algorithms were subsequently developed, by Jerome H. Friedman, (in 1999 and later in 2001) simultaneously with the more general functional gradient boosting perspective of Llew Mason, Jonathan Baxter, Peter Bartlett and Marcus Frean.
The latter two papers introduced the view of boosting algorithms as iterative functional gradient descent algorithms. That is, algorithms that optimize a cost function over function space by iteratively choosing a function (weak hypothesis) that points in the negative gradient direction. This functional gradient view of boosting has led to the development of boosting algorithms in many areas of machine learning and statistics beyond regression and classification.


## Informal introduction
(This section follows the exposition by Cheng Li.)
Like other boosting methods, gradient boosting combines weak "learners" into a single strong learner iteratively. It is easiest to explain in the least-squares regression setting, where the goal is to teach a model 
  
    
      
        F
      
    
    {\displaystyle F}
  
 to predict values of the form 
  
    
      
        
          
            
              y
              ^
            
          
        
        =
        F
        (
        x
        )
      
    
    {\displaystyle {\hat {y}}=F(x)}
  
 by minimizing the mean squared error 
  
    
      
        
          
            
              1
              n
            
          
        
        
          ∑
          
            i
          
        
        (
        
          
            
              
                y
                ^
              
            
          
          
            i
          
        
        −
        
          y
          
            i
          
        
        
          )
          
            2
          
        
      
    
    {\displaystyle {\tfrac {1}{n}}\sum _{i}({\hat {y}}_{i}-y_{i})^{2}}
  
, where 
  
    
      
        i
      
    
    {\displaystyle i}
  
 indexes over some training set of size 
  
    
      
        n
      
    
    {\displaystyle n}
  
 of actual values of the output variable 
  
    
      
        y
      
    
    {\displaystyle y}
  
:

  
    
      
        
          
            
              
                y
                ^
              
            
          
          
            i
          
        
        =
      
    
    {\displaystyle {\hat {y}}_{i}=}
  
 the predicted value 
  
    
      
        F
        (
        
          x
          
            i
          
        
        )
      
    
    {\displaystyle F(x_{i})}
  

  
    
      
        
          y
          
            i
          
        
        =
      
    
    {\displaystyle y_{i}=}
  
 the observed value

  
    
      
        n
        =
      
    
    {\displaystyle n=}
  
 the size of the sample, i.e. the number of observations in 
  
    
      
        y
      
    
    {\displaystyle y}
  

If the algorithm has 
  
    
      
        M
      
    
    {\displaystyle M}
  
 stages, at each stage 
  
    
      
        m
      
    
    {\displaystyle m}
  
 (
  
    
      
        1
        ≤
        m
        ≤
        M
      
    
    {\displaystyle 1\leq m\leq M}
  
), suppose some imperfect model 
  
    
      
        
          F
          
            m
          
        
      
    
    {\displaystyle F_{m}}
  
 (for low 
  
    
      
        m
      
    
    {\displaystyle m}
  
, this model may simply predict 
  
    
      
        
          
            
              
                y
                ^
              
            
          
          
            i
          
        
      
    
    {\displaystyle {\hat {y}}_{i}}
  
 to be  
  
    
      
        
          
            
              y
              ¯
            
          
        
      
    
    {\displaystyle {\bar {y}}}
  
, the mean of 
  
    
      
        y
      
    
    {\displaystyle y}
  
). In order to improve 
  
    
      
        
          F
          
            m
          
        
      
    
    {\displaystyle F_{m}}
  
, our algorithm should add some new estimator, 
  
    
      
        
          h
          
            m
          
        
        (
        x
        )
      
    
    {\displaystyle h_{m}(x)}
  
. Thus,

  
    
      
        
          F
          
            m
            +
            1
          
        
        (
        
          x
          
            i
          
        
        )
        =
        
          F
          
            m
          
        
        (
        
          x
          
            i
          
        
        )
        +
        
          h
          
            m
          
        
        (
        
          x
          
            i
          
        
        )
        =
        
          y
          
            i
          
        
      
    
    {\displaystyle F_{m+1}(x_{i})=F_{m}(x_{i})+h_{m}(x_{i})=y_{i}}
  

or, equivalently,

  
    
      
        
          h
          
            m
          
        
        (
        
          x
          
            i
          
        
        )
        =
        
          y
          
            i
          
        
        −
        
          F
          
            m
          
        
        (
        
          x
          
            i
          
        
        )
        .
      
    
    {\displaystyle h_{m}(x_{i})=y_{i}-F_{m}(x_{i}).}
  

Therefore, gradient boosting will fit 
  
    
      
        
          h
          
            m
          
        
      
    
    {\displaystyle h_{m}}
  
 to the residual 
  
    
      
        
          y
          
            i
          
        
        −
        
          F
          
            m
          
        
        (
        
          x
          
            i
          
        
        )
      
    
    {\displaystyle y_{i}-F_{m}(x_{i})}
  
. As in other boosting variants, each 
  
    
      
        
          F
          
            m
            +
            1
          
        
      
    
    {\displaystyle F_{m+1}}
  
 attempts to correct the errors of its predecessor 
  
    
      
        
          F
          
            m
          
        
      
    
    {\displaystyle F_{m}}
  
. A generalization of this idea to loss functions other than squared error, and to classification and ranking problems, follows from the observation that residuals 
  
    
      
        
          h
          
            m
          
        
        (
        
          x
          
            i
          
        
        )
      
    
    {\displaystyle h_{m}(x_{i})}
  
 for a given model are proportional to the negative gradients of the mean squared error (MSE) loss function (with respect to 
  
    
      
        F
        (
        
          x
          
            i
          
        
        )
      
    
    {\displaystyle F(x_{i})}
  
):

  
    
      
        
          L
          
            
              M
              S
              E
            
          
        
        =
        
          
            1
            n
          
        
        
          ∑
          
            i
            =
            1
          
          
            n
          
        
        
          
            (
            
              
                y
                
                  i
                
              
              −
              F
              (
              
                x
                
                  i
                
              
              )
            
            )
          
          
            2
          
        
      
    
    {\displaystyle L_{\rm {MSE}}={\frac {1}{n}}\sum _{i=1}^{n}\left(y_{i}-F(x_{i})\right)^{2}}
  

  
    
      
        −
        
          
            
              ∂
              
                L
                
                  
                    M
                    S
                    E
                  
                
              
            
            
              ∂
              F
              (
              
                x
                
                  i
                
              
              )
            
          
        
        =
        
          
            2
            n
          
        
        (
        
          y
          
            i
          
        
        −
        F
        (
        
          x
          
            i
          
        
        )
        )
        =
        
          
            2
            n
          
        
        
          h
          
            m
          
        
        (
        
          x
          
            i
          
        
        )
        .
      
    
    {\displaystyle -{\frac {\partial L_{\rm {MSE}}}{\partial F(x_{i})}}={\frac {2}{n}}(y_{i}-F(x_{i}))={\frac {2}{n}}h_{m}(x_{i}).}
  

So, gradient boosting could be generalized to a gradient descent algorithm by plugging in a different loss and its gradient.


## Algorithm
Many supervised learning problems involve an output variable y and a vector of input variables x, related to each other with some probabilistic distribution. The goal is to find some function 
  
    
      
        
          
            
              F
              ^
            
          
        
        (
        x
        )
      
    
    {\displaystyle {\hat {F}}(x)}
  
 that best approximates the output variable from the values of input variables. This is formalized by introducing some loss function 
  
    
      
        L
        (
        y
        ,
        F
        (
        x
        )
        )
      
    
    {\displaystyle L(y,F(x))}
  
 and minimizing it in expectation:

  
    
      
        
          
            
              F
              ^
            
          
        
        =
        
          argmin
          
            F
          
        
        ⁡
        
          
            E
          
          
            x
            ,
            y
          
        
        [
        L
        (
        y
        ,
        F
        (
        x
        )
        )
        ]
        .
      
    
    {\displaystyle {\hat {F}}=\operatorname {argmin} \limits _{F}\mathbb {E} _{x,y}[L(y,F(x))].}
  

The gradient boosting method assumes a real-valued y. It seeks an approximation 
  
    
      
        
          
            
              F
              ^
            
          
        
        (
        x
        )
      
    
    {\displaystyle {\hat {F}}(x)}
  
 in the form of a weighted sum of M functions 
  
    
      
        
          h
          
            m
          
        
        (
        x
        )
      
    
    {\displaystyle h_{m}(x)}
  
 from some class 
  
    
      
        
          
            H
          
        
      
    
    {\displaystyle {\mathcal {H}}}
  
, called base (or weak) learners:

  
    
      
        
          
            
              F
              ^
            
          
        
        (
        x
        )
        =
        
          ∑
          
            m
            =
            1
          
          
            M
          
        
        
          γ
          
            m
          
        
        
          h
          
            m
          
        
        (
        x
        )
        +
        
          
            const
          
        
        ,
      
    
    {\displaystyle {\hat {F}}(x)=\sum _{m=1}^{M}\gamma _{m}h_{m}(x)+{\mbox{const}},}
  

where 
  
    
      
        
          γ
          
            m
          
        
      
    
    {\displaystyle \gamma _{m}}
  
 is the weight at stage 
  
    
      
        m
      
    
    {\displaystyle m}
  
. We are usually given a training set 
  
    
      
        {
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
        }
      
    
    {\displaystyle \{(x_{1},y_{1}),\dots ,(x_{n},y_{n})\}}
  
 of known values of x and corresponding values of y. In accordance with the empirical risk minimization principle, the method tries to find an approximation 
  
    
      
        
          
            
              F
              ^
            
          
        
        (
        x
        )
      
    
    {\displaystyle {\hat {F}}(x)}
  
 that minimizes the average value of the loss function on the training set, i.e., minimizes the empirical risk. It does so by starting with a model, consisting of a constant function 
  
    
      
        
          F
          
            0
          
        
        (
        x
        )
      
    
    {\displaystyle F_{0}(x)}
  
, and incrementally expands it in a greedy fashion:

  
    
      
        
          F
          
            0
          
        
        (
        x
        )
        =
        
          
            
              arg
              ⁡
              min
            
            
              
                h
                
                  0
                
              
              ∈
              
                
                  H
                
              
            
          
        
        
          ∑
          
            i
            =
            1
          
          
            n
          
        
        
          L
          (
          
            y
            
              i
            
          
          ,
          
            h
            
              0
            
          
          (
          
            x
            
              i
            
          
          )
          )
        
        ,
      
    
    {\displaystyle F_{0}(x)={\underset {h_{0}\in {\mathcal {H}}}{\arg \min }}\sum _{i=1}^{n}{L(y_{i},h_{0}(x_{i}))},}
  

  
    
      
        
          F
          
            m
          
        
        (
        x
        )
        =
        
          F
          
            m
            −
            1
          
        
        (
        x
        )
        +
        
          (
          
            
              
                
                  a
                  r
                  g
                  
                  m
                  i
                  n
                
                
                  
                    h
                    
                      m
                    
                  
                  ∈
                  
                    
                      H
                    
                  
                
              
            
            
  