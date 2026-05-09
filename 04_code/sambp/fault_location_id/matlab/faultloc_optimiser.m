function [theta_hat, info] = faultloc_optimiser(H_meas, opts)
%FAULTLOC_OPTIMISER  Two-stage joint estimator of (alpha, R_x).
%
%   [theta_hat, info] = faultloc_optimiser(H_meas)
%   [theta_hat, info] = faultloc_optimiser(H_meas, opts)
%
%   Inputs
%     H_meas   Complex single-bin admittance at omega_0, scalar.
%     opts     Struct of hyperparameters (all optional):
%        n_alpha    grid count along alpha    (default 100)
%        n_Rx       grid count along R_x      (default 50)
%        n_seeds    number of multi-start seeds from Stage 1 (default 3)
%        h_alpha    finite-difference step in alpha          (default 1e-4)
%        h_Rx       finite-difference step in R_x  [ohm]     (default 1e-1)
%        beta       Armijo backtracking ratio                 (default 0.5)
%        c1         Armijo sufficient-decrease constant       (default 1e-4)
%        max_iter   Stage-2 iteration cap                     (default 2000)
%        tol_J      target cost for early termination         (default 1e-12)
%        bounds     [a_lo a_hi Rx_lo Rx_hi]   (default [0.05 0.95 100 5000])
%        f0, Fs     forward-model frequencies                 (default 50, 10e3)
%
%   Outputs
%     theta_hat = [alpha_hat; Rx_hat]
%     info has fields: J_min, n_iters, kappa_jac, cpu_time_s, history (optional).

    if nargin < 2, opts = struct(); end
    n_alpha   = getfield_default(opts, 'n_alpha',   100);
    n_Rx      = getfield_default(opts, 'n_Rx',      50);
    n_seeds   = getfield_default(opts, 'n_seeds',   3);
    h_alpha   = getfield_default(opts, 'h_alpha',   1e-4);
    h_Rx      = getfield_default(opts, 'h_Rx',      1e-1);
    beta      = getfield_default(opts, 'beta',      0.5);
    c1        = getfield_default(opts, 'c1',        1e-4);
    max_iter  = getfield_default(opts, 'max_iter',  2000);
    tol_J     = getfield_default(opts, 'tol_J',     1e-12);
    bounds    = getfield_default(opts, 'bounds',    [0.05 0.95 100 5000]);
    f0        = getfield_default(opts, 'f0',        50);
    omega0    = 2*pi*f0;

    a_lo  = bounds(1); a_hi  = bounds(2);
    Rx_lo = bounds(3); Rx_hi = bounds(4);

    cost = @(theta) cost_at(theta, H_meas, omega0);

    t_start = tic;

    % ---- Stage 1: coarse grid + top-N seeds --------------------------------
    aa = linspace(a_lo, a_hi, n_alpha);
    Rx = linspace(Rx_lo, Rx_hi, n_Rx);
    Jgrid = zeros(n_alpha, n_Rx);
    for i = 1:n_alpha
        for j = 1:n_Rx
            Jgrid(i, j) = cost([aa(i); Rx(j)]);
        end
    end
    [Jsort, idx] = sort(Jgrid(:));
    seeds = zeros(2, n_seeds);
    for k = 1:n_seeds
        [ii, jj] = ind2sub(size(Jgrid), idx(k));
        seeds(:, k) = [aa(ii); Rx(jj)];
    end

    % ---- Stage 2: gradient descent w/ Armijo on each seed -----------------
    best_J     = Inf;
    best_theta = seeds(:, 1);
    best_info  = struct('n_iters', 0, 'kappa_jac', NaN);
    for s = 1:n_seeds
        [theta, J, n_it, kjac] = grad_descent( ...
            cost, seeds(:, s), [a_lo; Rx_lo], [a_hi; Rx_hi], ...
            h_alpha, h_Rx, beta, c1, max_iter, tol_J);
        if J < best_J
            best_J     = J;
            best_theta = theta;
            best_info  = struct('n_iters', n_it, 'kappa_jac', kjac);
        end
    end

    theta_hat = best_theta;
    info = struct( ...
        'J_min',      best_J, ...
        'n_iters',    best_info.n_iters, ...
        'kappa_jac',  best_info.kappa_jac, ...
        'cpu_time_s', toc(t_start), ...
        'stage1_J0',  Jsort(1));
end


% ---------------------------------------------------------------------------
function [theta, J_at, n_it, kjac] = grad_descent( ...
        fun, theta, lo, hi, h_a, h_R, beta, c1, max_iter, tol_J)
    J_at = fun(theta);
    n_it = 0;
    kjac = NaN;
    for k = 1:max_iter
        n_it = k;
        if J_at < tol_J, break; end
        % Central FD gradient (Phase 0: WP2.4 replaces with closed-form).
        ea = [h_a; 0];
        eR = [0;  h_R];
        Ja_p = fun(theta + ea);  Ja_m = fun(theta - ea);
        JR_p = fun(theta + eR);  JR_m = fun(theta - eR);
        g    = [(Ja_p - Ja_m)/(2*h_a); (JR_p - JR_m)/(2*h_R)];
        H    = diag([(Ja_p - 2*J_at + Ja_m)/h_a^2, ...
                     (JR_p - 2*J_at + JR_m)/h_R^2]);
        if any(diag(H) <= 0)
            kjac = NaN;
            p = -g;                     % steepest descent fallback
        else
            kjac = max(diag(H)) / min(diag(H));
            p = -H \ g;                 % diagonal Newton
            if g.' * p >= 0, p = -g; end
        end
        opts = struct('step0', 1.0, 'beta', beta, 'c1', c1, 'max_iter', 30);
        [step, lsinfo] = armijo(fun, theta, p, J_at, g, opts);
        if ~lsinfo.success, break; end
        theta_new = clip2(theta + step*p, lo, hi);
        J_new = fun(theta_new);
        if J_new >= J_at, break; end
        theta = theta_new; J_at = J_new;
    end
end

function J = cost_at(theta, H_meas, omega0)
    [A, B, C, D] = faultloc_pi_state_space(theta(1), theta(2));
    H = C * ((1j*omega0*eye(size(A)) - A) \ B) + D;
    e = H_meas - H;
    J = real(e)^2 + imag(e)^2;
end

function y = clip2(x, lo, hi)
    y = min(max(x, lo), hi);
end

function v = getfield_default(s, name, default_value)
    if isfield(s, name) && ~isempty(s.(name))
        v = s.(name);
    else
        v = default_value;
    end
end
