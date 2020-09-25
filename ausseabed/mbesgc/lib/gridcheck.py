'''
Definition of Grid Checks implemented in mbesgc
'''


class GridCheckState(str, Enum):
    cs_pass = 'pass'
    cs_warning = 'warning'
    cs_fail = 'fail'


class GridCheckResult:
    '''
    Encapsulates the various outputs from a grid check
    '''
    def __init__(
            self,
            state: GridCheckState,
            messages: List = []):
        self.state = state
        self.messages = messages


class GridCheck:
    '''
    Base class for all grid checks
    '''

    def run(
            depth,
            density,
            uncertainty,
            progress_callback=None):
        '''
        Abstract function definition for how each check should implement its
        run method.

        Args:
            depth (numpy): Depth/elevation data
            depth (numpy): Density data
            uncertainty (numpy): Uncertainty data
            progress_callback (function): optional callback function to
                indicate progress to caller

        Returns:
            nothing?

        '''
        raise NotImplementedError
