"""
The customized image URL processing engine.

Author: Qing Wang

"""

import re

LC_LIST = ["a", "b", "c", "d", "e", "f", "g"]
CAP_LIST = ["A", "B", "C", "D", "E", "F", "G"]
NUM_LIST = ["0", "1", "2", "3", "4", "5", "6"]


class URLProcessor:
    """
    Class for URLProcessor.
    """

    def __init__(self, data_url, page_num):
        """
        Constructor method.
        """
        super(URLProcessor, self).__init__()
        self.pnum = page_num
        self.data_url = data_url
        self.template = self._generate_template(self.data_url)

    def _generate_template(self, url):
        """
        Generate the template string from url.
        """
        fn = url.split("/")[-1]
        str_to_replaced = re.findall(r"\d+", fn)
        self.num_vars = len(str_to_replaced)
        self.n_digits = [len(s) for s in str_to_replaced]
        rep = {}
        for index, item in enumerate(str_to_replaced):
            rep[item] = "{var%i}" % index
        # use these three lines to do the replacement
        rep = dict((re.escape(k), v) for k, v in rep.items())
        pattern = re.compile("|".join(rep.keys()))
        text = pattern.sub(lambda m: rep[re.escape(m.group(0))], url)
        return text

    def normal_url_list(self):
        """
        Generate normal url list for iteration.
        """
        for i in range(0, self.pnum + 1):
            rep_dict = {
                "var%i" % t: str(i).zfill(self.n_digits[t])
                for t in range(self.num_vars)
            }
            yield self.template.format(**rep_dict)

    def special_url_list(self, sep=""):
        """
        Generate special urls for iteration.
        """
        sp_c_list = LC_LIST + CAP_LIST + NUM_LIST
        for c in sp_c_list:
            if sep:
                rep_dict = {
                    "var%i" % t: "0".zfill(self.n_digits[t])
                    if t < self.num_vars - 1
                    else "0".zfill(self.n_digits[t]) + sep + c
                    for t in range(self.num_vars)
                }
            else:
                rep_dict = {
                    "var%i" % t: "0".zfill(self.n_digits[t])
                    if t < self.num_vars - 1
                    else "0".zfill(self.n_digits[t]) + c
                    for t in range(self.num_vars)
                }
            yield self.template.format(**rep_dict)
