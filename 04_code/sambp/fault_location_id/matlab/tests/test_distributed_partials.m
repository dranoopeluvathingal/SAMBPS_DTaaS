classdef test_distributed_partials < matlab.unittest.TestCase
    %TEST_DISTRIBUTED_PARTIALS  WP2.2 - symbolic dH/dalpha, dH/dRx
    %vs Python implementation, agreement to 1e-9.
    %
    %   The Python module
    %   `inverse_estimation/faultloc_analytical_gradients.py` ships
    %   the closed-form partials.  This MATLAB testcase derives the
    %   same partials symbolically (via `sym/diff` on the same
    %   cosh/sinh ABCD chain), evaluates at the three brief test
    %   points, and asserts agreement with the Python output to
    %   1e-9 relative.
    %
    %   The Python values are produced by
    %       python -c "from sambp_fault_location_id.inverse_estimation
    %                  .faultloc_analytical_gradients import dH_dtheta
    %                  print(dH_dtheta(...))"
    %   and shipped here as hard-coded reference complex numbers.
    %   When the Python implementation changes, regenerate via the
    %   one-liner in `update_python_reference()` below.
    %
    %   This test requires Symbolic Math Toolbox.  Outside the
    %   toolbox the testcase is skipped with a clear message.

    properties (Constant)
        % Per-km defaults (mirror of Python module)
        R_per_km = 0.0728;
        L_per_km = 0.927e-3;
        C_per_km = 11.6e-9;
        G_per_km = 0.0;
        L_total  = 100.0;
        R_load   = 1.0e6;
        omega    = 2 * pi * 50;
        tol_rel  = 1e-9;
        cases    = {[0.2, 100];   [0.5, 1000];   [0.8, 5000]};
        % Python reference values (regenerate via update_python_reference).
        % Generated 2026-05-10 from
        % inverse_estimation/faultloc_analytical_gradients.py.
        % dH_dalpha:
        py_dH_da = { ...
            -8.7072098062e-04 - 2.7905237620e-03i; ...    % @(0.2, 100)
            +2.3353181007e-06 - 3.1940811296e-05i; ...    % @(0.5, 1000)
            +5.4263621612e-07 - 1.4063508521e-06i  ...    % @(0.8, 5000)
        };
        % dH_dRx:
        py_dH_dR = { ...
            -9.6539628521e-05 + 1.1235065199e-05i; ...    % @(0.2, 100)
            -9.9995334345e-07 + 3.1147010277e-08i; ...    % @(0.5, 1000)
            -4.0311371481e-08 + 4.8157882405e-10i  ...    % @(0.8, 5000)
        };
    end

    methods (Test)

        function symbolicDerivativesMatchPython(testCase)
            % Skip if the Symbolic Math Toolbox is not installed
            available = ver;
            available_names = {available.Name};
            if ~any(strcmp(available_names, 'Symbolic Math Toolbox'))
                testCase.assumeFail( ...
                    'Symbolic Math Toolbox not installed; skipping');
            end

            syms alpha Rx omega real
            syms R_per_km L_per_km C_per_km G_per_km L_total R_load real positive

            z = R_per_km + 1j*omega*L_per_km;
            y = G_per_km + 1j*omega*C_per_km;
            gamma_v = sqrt(z*y);
            Z_c = sqrt(z/y);
            L1 = alpha * L_total;
            L2 = (1 - alpha) * L_total;
            gL1 = gamma_v * L1;
            gL2 = gamma_v * L2;
            ch1 = cosh(gL1);  sh1 = sinh(gL1);
            ch2 = cosh(gL2);  sh2 = sinh(gL2);
            T1 = [ch1, Z_c*sh1; sh1/Z_c, ch1];
            T2 = [ch2, Z_c*sh2; sh2/Z_c, ch2];
            Tf = [sym(1), sym(0); 1/Rx, sym(1)];
            Tl = [sym(1), sym(0); 1/R_load, sym(1)];
            T_end = T1 * Tf * T2 * Tl;
            H = T_end(2, 1) / T_end(1, 1);

            dH_da_sym = simplify(diff(H, alpha));
            dH_dR_sym = simplify(diff(H, Rx));

            for k = 1:numel(testCase.cases)
                a_val = testCase.cases{k}(1);
                R_val = testCase.cases{k}(2);
                py_a  = testCase.py_dH_da{k};
                py_R  = testCase.py_dH_dR{k};

                ml_a = double(subs(dH_da_sym, ...
                    {alpha, Rx, omega, R_per_km, L_per_km, ...
                     C_per_km, G_per_km, L_total, R_load}, ...
                    {a_val, R_val, testCase.omega, testCase.R_per_km, ...
                     testCase.L_per_km, testCase.C_per_km, ...
                     testCase.G_per_km, testCase.L_total, testCase.R_load}));
                ml_R = double(subs(dH_dR_sym, ...
                    {alpha, Rx, omega, R_per_km, L_per_km, ...
                     C_per_km, G_per_km, L_total, R_load}, ...
                    {a_val, R_val, testCase.omega, testCase.R_per_km, ...
                     testCase.L_per_km, testCase.C_per_km, ...
                     testCase.G_per_km, testCase.L_total, testCase.R_load}));

                rel_a = abs(ml_a - py_a) / abs(ml_a);
                rel_R = abs(ml_R - py_R) / abs(ml_R);

                testCase.verifyLessThan(rel_a, testCase.tol_rel, ...
                    sprintf(['dH/dalpha @(a=%.2f, R=%.0f) rel err = %.3e ', ...
                             '>= tol %.0e'], a_val, R_val, rel_a, testCase.tol_rel));
                testCase.verifyLessThan(rel_R, testCase.tol_rel, ...
                    sprintf(['dH/dRx    @(a=%.2f, R=%.0f) rel err = %.3e ', ...
                             '>= tol %.0e'], a_val, R_val, rel_R, testCase.tol_rel));
            end
        end

    end

    methods (Static)

        function update_python_reference()
            %UPDATE_PYTHON_REFERENCE  Regenerate hard-coded py_dH_da and
            %py_dH_dR arrays.  Invoke when the Python module changes.
            disp('Run from the project root:');
            disp('');
            disp('  .venv/bin/python -c "');
            disp('  from sambp_fault_location_id.inverse_estimation' ...
                 '.faultloc_analytical_gradients import dH_dtheta');
            disp('  import numpy as np');
            disp('  for a, R in [(0.2, 100), (0.5, 1000), (0.8, 5000)]:');
            disp('      da, dR = dH_dtheta(a, R, 2*np.pi*50)');
            disp('      print(f''({da.real:.4e}+{da.imag:.4e}j)'', ');
            disp('            f''({dR.real:.4e}+{dR.imag:.4e}j)'')');
            disp('  "');
        end

    end
end
