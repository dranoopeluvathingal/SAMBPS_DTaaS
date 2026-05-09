function [step, info] = armijo(fun, x, p, J0, grad, opts)
%ARMIJO  Backtracking Armijo line search.
%
%   [step, info] = armijo(fun, x, p, J0, grad, opts)
%
%   Generic helper: takes the cost handle FUN, the current point X, a
%   descent direction P (column vector, dot(P, GRAD) < 0), the current
%   cost J0 = FUN(X), and the gradient GRAD at X, and returns a step
%   length STEP that satisfies the Armijo sufficient-decrease condition
%
%       FUN(X + STEP*P) <= J0 + c1*STEP*<GRAD,P>
%
%   OPTS fields (all optional with defaults):
%       step0    initial step length          (default 1.0)
%       c1       Armijo constant in (0,1)     (default 1e-4)
%       beta     backtracking ratio in (0,1)  (default 0.5)
%       max_iter maximum backtracks           (default 30)
%
%   INFO.iter is the number of backtracks taken; INFO.success is true
%   if the condition was met.  If the search fails, STEP returns the
%   smallest step tried and INFO.success is false.
%
%   Generic helper - kept under its original name and parked under
%   matlab/utils/ per the SAMBPS convention for cross-project utilities.

    if nargin < 6, opts = struct(); end
    step0    = getfield_default(opts, 'step0',    1.0);
    c1       = getfield_default(opts, 'c1',       1e-4);
    beta     = getfield_default(opts, 'beta',     0.5);
    max_iter = getfield_default(opts, 'max_iter', 30);

    g_dot_p = grad(:).' * p(:);
    if g_dot_p >= 0
        error('armijo:notDescent', ...
            'Direction is not a descent direction (g.''p = %.3e >= 0)', g_dot_p);
    end

    step = step0;
    for k = 1:max_iter
        J_try = fun(x + step * p);
        if J_try <= J0 + c1 * step * g_dot_p
            info = struct('iter', k, 'success', true);
            return;
        end
        step = beta * step;
    end
    info = struct('iter', max_iter, 'success', false);
end


function v = getfield_default(s, name, default_value)
    if isfield(s, name) && ~isempty(s.(name))
        v = s.(name);
    else
        v = default_value;
    end
end
