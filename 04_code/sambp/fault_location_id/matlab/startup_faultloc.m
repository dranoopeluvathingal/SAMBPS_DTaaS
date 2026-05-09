function startup_faultloc()
%STARTUP_FAULTLOC  SAMBPS DTaaS - fault_location_id MATLAB bootstrap.
%
%   Adds the project root and the matlab/ folder (and its tests subfolder)
%   to the MATLAB path, prints the MATLAB release, and reports which of
%   the four toolboxes required by the v3 execution plan are available.
%   Missing toolboxes raise a non-fatal warning that names the toolbox so
%   that the developer can decide whether to skip the dependent WP for
%   now or install the licence.
%
%   Required toolboxes
%   ------------------
%       Symbolic Math Toolbox       WP0.5  (sym/eig regression test;
%                                   closed-form derivation of dH/dalpha,
%                                   dH/dRx for distributed-parameter
%                                   model)
%       Signal Processing Toolbox   WP3.5  (Taylor-Fourier phasor
%                                   estimator; non-stationary HIF
%                                   waveform analysis)
%       Control System Toolbox      WP0.5 / WP2.1  (state-space build,
%                                   transfer-function evaluation)
%       Optimization Toolbox        WP2.4  (Armijo line-search reference
%                                   implementation; constrained
%                                   gradient-descent benchmark)
%
%   This function is invoked from `matlab/run_smoke.m` and from the
%   `matlab-smoke` Makefile target.

    here = fileparts(mfilename('fullpath'));   % .../fault_location_id/matlab
    root = fileparts(here);                    % .../fault_location_id

    addpath(root);
    addpath(here);
    addpath(fullfile(here, 'tests'));

    fprintf('SAMBPS DTaaS - fault_location_id - MATLAB bootstrap\n');
    try
        release_str = char(matlabRelease.Release);     % R2022a+
    catch
        release_str = version('-release');             % older releases
    end
    fprintf('  MATLAB release: %s (version %s)\n', release_str, version);
    fprintf('  faultloc package version: %s\n', faultloc.version());
    fprintf('  Project root: %s\n', root);
    fprintf('\n');

    required = { ...
        'Symbolic Math Toolbox', ...
        'Signal Processing Toolbox', ...
        'Control System Toolbox', ...
        'Optimization Toolbox' ...
    };

    available_struct = ver;
    available_names = {available_struct.Name};

    fprintf('Toolbox availability:\n');
    missing = {};
    for k = 1:numel(required)
        name = required{k};
        if any(strcmp(available_names, name))
            fprintf('  [OK]       %s\n', name);
        else
            fprintf('  [MISSING]  %s\n', name);
            missing{end+1} = name; %#ok<AGROW>
        end
    end

    if ~isempty(missing)
        warning('faultloc:missingToolbox', ...
            ['Missing required toolbox(es): %s. ', ...
             'Install or licence them before running the dependent ', ...
             'work packages (see docstring above).'], ...
            strjoin(missing, ', '));
    end
end
